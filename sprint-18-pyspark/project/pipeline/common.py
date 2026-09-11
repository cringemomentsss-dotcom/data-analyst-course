"""Общее для скриптов пайплайна: сессия Spark, настроенная на MinIO.

Импортируется из скриптов проекта:

    from common import get_spark, RAW

Запуск скрипта — через spark-submit внутри контейнера:

    make spark-sh CMD='spark-submit --packages $(cat /course/sprint-18-pyspark/project/pipeline/packages.txt) \
        /course/sprint-18-pyspark/project/pipeline/твой_скрипт.py'
"""

from pyspark.sql import SparkSession

RAW = "s3a://raw"
LAKE = "s3a://lake"

S3_CONF = {
    "spark.hadoop.fs.s3a.endpoint": "http://minio:9000",
    "spark.hadoop.fs.s3a.access.key": "analyst",
    "spark.hadoop.fs.s3a.secret.key": "analyst123",
    "spark.hadoop.fs.s3a.path.style.access": "true",
    "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
    "spark.hadoop.fs.s3a.connection.ssl.enabled": "false",
    # MinIO не умеет часть проверок, которые S3A делает по умолчанию
    "spark.hadoop.fs.s3a.aws.credentials.provider":
        "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
}


def get_spark(app_name="pipeline", shuffle_partitions=8, quiet=True):
    """SparkSession в режиме local[*] с доступом к MinIO.

    shuffle_partitions по умолчанию 8, а не 200: на ноутбуке двести
    партиций для двух миллионов строк — это двести задач по десять
    тысяч строк каждая, и накладные расходы съедают всю выгоду.
    """
    builder = (SparkSession.builder
               .appName(app_name)
               .master("local[*]")
               .config("spark.sql.shuffle.partitions", shuffle_partitions)
               .config("spark.sql.session.timeZone", "UTC"))
    for k, v in S3_CONF.items():
        builder = builder.config(k, v)
    spark = builder.getOrCreate()
    if quiet:
        spark.sparkContext.setLogLevel("ERROR")
    return spark
