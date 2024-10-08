import logging

from cassandra.cluster import Cluster
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col
from pyspark.sql.types import StructField, StringType, StructType
import os
import sys

os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable


def create_keyspace(session):
    #create my keyspace
    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS spark_streams
        WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'}
    """)
    print("Keyspace created successfully!")

def create_table(session):
    #create my table
    session.execute("""
    CREATE TABLE IF NOT EXISTS spark_streams.create_user(
        id UUID PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        gender TEXT,
        address TEXT,
        post_code TEXT,
        email TEXT,
        username TEXT,
        dob TEXT,
        registered_date TEXT,
        phone TEXT,
        picture TEXT);
    """)
    print("Table created successfully!")

def insert_data(session, **kwargs):
    # insert data
    print("Inserting data...")

    user_id = kwargs.get('id')
    first_name = kwargs.get('first_name')
    last_name = kwargs.get('last_name')
    gender = kwargs.get('gender')
    address = kwargs.get('address')
    post_code = kwargs.get('post_code')
    email = kwargs.get('email')
    username = kwargs.get('username')
    dob = kwargs.get('dob')
    registered_date = kwargs.get('registered_date')
    phone = kwargs.get('phone')
    picture = kwargs.get('picture')

    try:
        session.execute("""
                    INSERT INTO spark_streams.created_users(id, first_name, last_name, gender, address, 
                        post_code, email, username, dob, registered_date, phone, picture)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, first_name, last_name, gender, address,
                      post_code, email, username, dob, registered_date, phone, picture))
        logging.info(f"Data inserted for {first_name} {last_name}")
    except Exception as e:
        logging.error(f"Couldn't insert data due to {e}")

def create_spark_connection():
    # create spark connection
    s_conn = None
    try:
        s_conn = SparkSession.builder \
            .appName('SparkDataStreaming') \
            .config('spark.jars.packages', 'com.datastax.spark:spark-cassandra-connector_2.13:3.4.1,'
                                            'org.apache.spark:spark-sql-kafka-0-10_2.13:3.4.1,'
                                            'org.scala-lang:scala-library:2.12.17') \
            .config('spark.cassandra.connection.host', 'localhost') \
            .getOrCreate()
        s_conn.sparkContext.setLogLevel("ERROR")
        logging.info("Spark connection created successfully!")

    except Exception as e:
        logging.error(f"Couldn't create the spark session due to exception {e}")

    return s_conn

def connect_to_kafka(spark_conn):
    spark_df = None
    try:
        spark_df = spark_conn.readStream \
            .format('Kafka') \
            .option('kafka.bootstrap.servers', 'localhost:9092') \
            .option('subscribe', 'users_created') \
            .option('startingOffsets', 'earliest').load()
        logging.info("Kafka dataframe created successfully!")
    except Exception as e:
        logging.warning(f"Couldn't create kafka dataframe due to exception {e}")
        return None
    return spark_df

def create_cassandra_connection():
    #create cassandra connection
    try:
        cluster = Cluster(['localhost'])

        cassandra_session = cluster.connect()
        return cassandra_session
    except Exception as e:
        logging.error(f"Couldn't create cassandra session due to exception {e}")
        return None

def create_selected_df_from_kafka(spark_df):
    schema = StructType([
        StructField("id", StringType(), False),
        StructField("first_name", StringType(), False),
        StructField("last_name", StringType(), False),
        StructField("gender", StringType(), False),
        StructField("address", StringType(), False),
        StructField("post_code", StringType(), False),
        StructField("email", StringType(), False),
        StructField("username", StringType(), False),
        StructField("registered_date", StringType(), False),
        StructField("phone", StringType(), False),
        StructField("picture", StringType(), False)
    ])

    try:
        sel = spark_df.selectExpr("CAST(value AS STRING)") \
            .select(from_json(col("value"), schema).alias("data")).select("data.*")
        logging.info("Successfully created selected DataFrame from Kafka")
        print(sel)
        return sel
    except Exception as e:
        logging.error(f"Error in create_selected_df_from_kafka: {e}")
        return None

if __name__ == "__main__":
    spark_conn = create_spark_connection()

    if spark_conn is not None:
        #connect to kafka with spark
        df = connect_to_kafka(spark_conn)
        if df is not None:
            selected_df = create_selected_df_from_kafka(df)
            session  = create_cassandra_connection()

            if session is not None:
                create_keyspace(session)
                create_table(session)
                #insert_data(session)

                streaming_query = selected_df.writeStream.format("org.apache.spark.sql.cassandra")\
                                .option('checkpointLocation', '/tmp/checkpoints')\
                                .option('keyspace', 'spark_streams')\
                                .option('table', 'created_users').start()
                streaming_query.awaitTermination()
