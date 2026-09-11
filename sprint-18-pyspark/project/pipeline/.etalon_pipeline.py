"""Эталонный пайплайн проекта спринта 18. Не подглядывать до сдачи.

Считает всю статистику одним проходом: десять отдельных .count() —
это десять полных перечитываний исходных данных.
"""
import sys
sys.path.insert(0, "/course/sprint-18-pyspark/project/pipeline")

from pyspark.sql import functions as F
from pyspark.sql.types import (StructType, StructField, StringType, LongType,
                               DecimalType)
from common import get_spark, RAW, LAKE

FROM_TS, TO_TS = "2026-06-01 00:00:00", "2026-07-01 00:00:00"

spark = get_spark("etalon-pipeline", shuffle_partitions=16)

SCHEMA = StructType([
    StructField("event_id", LongType(), False),
    StructField("user_id", StringType(), True),
    StructField("ts", StringType(), True),
    StructField("event", StringType(), True),
    StructField("session_id", LongType(), True),
    StructField("device", StringType(), True),
    StructField("country", StringType(), True),
    StructField("revenue", StringType(), True),
    StructField("utm_source", StringType(), True),
    StructField("product_id", LongType(), True),
    StructField("_corrupt_record", StringType(), True),
])

raw = (spark.read.schema(SCHEMA)
       .option("mode", "PERMISSIVE")
       .option("columnNameOfCorruptRecord", "_corrupt_record")
       .json(f"{RAW}/events/"))

# Слой staging. Он нужен не только для порядка: Spark запрещает запрос,
# который ссылается ТОЛЬКО на _corrupt_record, а Catalyst выбрасывает
# «настоящий» столбец, если тот не влияет на результат. Записав разобранное
# в Parquet, мы снимаем ограничение — и заодно перестаём перечитывать
# и переразбирать JSON на каждом действии.
(raw.withColumn("dt_file", F.to_date(F.substring(F.col("ts"), 1, 10)))
    .write.mode("overwrite").partitionBy("dt_file")
    .parquet(f"{LAKE}/staging/events"))

stg = spark.read.parquet(f"{LAKE}/staging/events")

stats = stg.agg(
    F.count("*").alias("total"),
    F.sum(F.when(F.col("_corrupt_record").isNotNull(), 1).otherwise(0)).alias("corrupt"),
).first()

clean = (stg.filter(F.col("_corrupt_record").isNull())
         .withColumn("user_id", F.col("user_id").cast("long"))
         .withColumn("event_ts", F.to_timestamp("ts", "yyyy-MM-dd'T'HH:mm:ss"))
         .withColumn("device", F.lower(F.trim(F.col("device"))))
         .withColumn("country", F.coalesce(F.col("country"), F.lit("unknown")))
         .withColumn("utm_source", F.coalesce(F.col("utm_source"), F.lit("direct")))
         .withColumn("revenue", F.coalesce(
             F.regexp_extract(F.col("revenue"), r"^\s*([0-9]+\.?[0-9]*)", 1)
              .cast(DecimalType(10, 2)),
             F.lit(0).cast(DecimalType(10, 2))))
         .drop("ts", "_corrupt_record"))

dedup = clean.dropDuplicates(["event_id"])

marked = dedup.withColumn(
    "bucket",
    F.when(F.col("event_ts") < F.lit(FROM_TS), "late")
     .when(F.col("event_ts") >= F.lit(TO_TS), "future")
     .otherwise("window"))

buckets = {r["bucket"]: r["n"] for r in
           marked.groupBy("bucket").agg(F.count("*").alias("n")).collect()}
after_dedup = sum(buckets.values())

in_window = marked.filter(F.col("bucket") == "window").drop("bucket")

users = (spark.read.option("header", True)
         .csv(f"{RAW}/dicts/users.csv")
         .select(F.col("user_id").cast("long"), F.col("plan")))

enriched = in_window.join(F.broadcast(users), on="user_id", how="left")

mart = (enriched
        .withColumn("dt", F.to_date("event_ts"))
        .groupBy("dt", "device", "plan")
        .agg(F.count("*").alias("events"),
             F.countDistinct("user_id").alias("users"),
             F.sum(F.when(F.col("event") == "purchase", 1).otherwise(0)).alias("purchases"),
             F.sum("revenue").alias("revenue")))

(mart.write.mode("overwrite").partitionBy("dt").parquet(f"{LAKE}/mart_daily"))

back = spark.read.parquet(f"{LAKE}/mart_daily")
summary = back.agg(F.count("*").alias("rows"),
                   F.sum("events").alias("events"),
                   F.sum("purchases").alias("purchases"),
                   F.sum("revenue").alias("revenue")).first()

print("=" * 54)
print(f"строк прочитано:            {stats['total']}")
print(f"битых записей:              {stats['corrupt']}")
print(f"после дедупликации:         {after_dedup}")
print(f"дублей удалено:             {stats['total'] - stats['corrupt'] - after_dedup}")
print(f"в окне [июнь):              {buckets.get('window', 0)}")
print(f"опоздавших (раньше окна):   {buckets.get('late', 0)}")
print(f"из будущего (позже окна):   {buckets.get('future', 0)}")
print(f"строк витрины:              {summary['rows']}")
print(f"событий в витрине:          {summary['events']}")
print(f"покупок:                    {summary['purchases']}")
print(f"выручка:                    {summary['revenue']}")
print("=" * 54)
spark.stop()
