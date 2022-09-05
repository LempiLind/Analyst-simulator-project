from datetime import datetime, timedelta
import pandas as pd
from io import StringIO
import requests
import pandahouse

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


# Функция для CH
def ch_get_df(query='Select 1', host='https://clickhouse.lab.karpov.courses', user='student', password='dpo_python_2020'):
    r = requests.post(host, data=query.encode("utf-8"), auth=(user, password), verify=False)
    result = pd.read_csv(StringIO(r.text), sep='\t')
    return result

# Дефолтные параметры, которые прокидываются в таски
default_args = {
    'owner': 'l-rusinova-9',
    'depends_on_past': False,
    'retries': 10,
    'retry_delay': timedelta(minutes=1),
    'start_date': datetime(2022, 7, 20),
}

# Интервал запуска DAG
schedule_interval = '0 0 * * *'

@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def dag_rusinova_6_final():
    
    @task()
    def extract_feed_actions():
        query = """SELECT 
                       toDate(time) AS event_date, 
                       user_id,
                       os,
                       gender,
                       age,
                       countIf(action='like') AS likes,
                       countIf(action='view') AS views
                    FROM 
                        simulator_20220720.feed_actions 
                    WHERE toDate(time) = yesterday()
                    GROUP BY
                        event_date, user_id, os, gender, age
                    
                    format TSVWithNames"""
        df_cube = ch_get_df(query=query)
        return df_cube    
    
    @task()
    def extract_message_actions():
        query = """SELECT * FROM
                    
                    (
                    SELECT
                    
                    CASE 
                    WHEN sender_date != '1970-01-01' THEN sender_date
                    ELSE reciever_date
                    END AS event_date,

                    CASE
                    WHEN sender_id > 0 THEN sender_id
                    ELSE reciever_id
                    END AS user_id,

                    CASE
                    WHEN sender_id > 0 THEN users1.gender
                    ELSE users2.gender
                    END AS gender,

                    CASE
                    WHEN sender_id > 0 THEN users1.age
                    ELSE users2.age
                    END AS age,

                    CASE
                    WHEN sender_id > 0 THEN users1.os
                    ELSE users2.os
                    END AS os,


                    messages_sent,
                    users_sent,
                    messages_received,
                    users_received

                    FROM

                      (
                      SELECT 
                        toDate(time) AS sender_date, user_id AS sender_id,
                        count(reciever_id) AS messages_sent, countDistinct(reciever_id) AS users_sent
                      FROM
                        simulator_20220720.message_actions
                      
                      GROUP BY sender_date, sender_id
                      ORDER BY sender_date, sender_id
                      ) AS senders

                      FULL OUTER JOIN

                      (
                      SELECT 
                        toDate(time) AS reciever_date, reciever_id,
                        count(user_id) AS messages_received, countDistinct(user_id) AS users_received
                      FROM
                        simulator_20220720.message_actions
                      
                      GROUP BY reciever_date, reciever_id
                      ORDER BY reciever_date, reciever_id
                      ) AS recievers

                      ON
                      senders.sender_id = recievers.reciever_id
                      AND senders.sender_date = recievers.reciever_date

                      JOIN

                      (
                      SELECT
                      DISTINCT user_id, gender, age, os
                      FROM simulator_20220720.message_actions
                      ) AS users1

                      ON senders.sender_id = users1.user_id

                      JOIN

                      (
                      SELECT
                      DISTINCT user_id, gender, age, os
                      FROM simulator_20220720.message_actions
                      ) AS users2

                      ON recievers.reciever_id = users2.user_id
                      )
                      
                    WHERE event_date = yesterday()
                      
                    format TSVWithNames"""
        df_cube = ch_get_df(query=query)
        return df_cube   

    @task
    def merge_all(df_feed, df_messages):
        df = df_feed.merge(df_messages, on=['user_id', 'event_date'], how='outer')

        df['gender'] = df.apply(lambda x: x['gender_x'] if x['gender_x']==x['gender_x'] else x['gender_y'], axis=1)
        df['os'] = df.apply(lambda x: x['os_x'] if x['os_x']==x['os_x'] else x['os_y'], axis=1)
        df['age'] = df.apply(lambda x: x['age_x'] if x['age_x']==x['age_x'] else x['age_y'], axis=1)

        df = df[['event_date', 'user_id', \
                 'gender', 'os', 'age', \
                 'likes', 'views', \
                 'messages_sent', 'users_sent', \
                 'messages_received', 'users_received']]
        
        return df
    
    @task
    def transform_os(df):
        df_os = df.copy()
        df_os = df_os.groupby(['event_date', 'os'])\
            .sum()\
            .reset_index()\
            .drop(columns = ['user_id', 'age', 'gender'])
        df_os['dimension'] = 'os'
        df_os.rename(columns = {'os': 'dimension_value'}, inplace=True)
        return df_os
    
    
    @task
    def transform_gender(df):
        df_gender = df.copy()
        df_gender = df_gender.groupby(['event_date', 'gender'])\
            .sum()\
            .reset_index()\
            .drop(columns = ['user_id', 'age'])
        df_gender['dimension'] = 'gender'
        df_gender.rename(columns = {'gender': 'dimension_value'}, inplace=True)
        return df_gender
    
    @task
    def transform_age(df):
        df_age = df.copy()
        df_age = df_age.groupby(['event_date', 'age'])\
            .sum()\
            .reset_index()\
            .drop(columns = ['user_id', 'gender'])
        df_age['dimension'] = 'age'
        df_age.rename(columns = {'age': 'dimension_value'}, inplace=True)
        return df_age
    
    @task
    def transform_final_df(df_gender, df_os, df_age):
        final_df = pd.concat([df_gender, df_os, df_age]).reset_index(drop=True)
        final_df = final_df[['event_date',
                             'views', 
                             'likes', 
                             'messages_sent',
                             'users_sent',
                             'messages_received',
                             'users_received',
                             'dimension',
                             'dimension_value']]        
        return final_df
    
    @task
    def load(final_df):
        connection_test = {
            'host': 'https://clickhouse.lab.karpov.courses',
            'password': '656e2b0c9c',
            'user': 'student-rw',
            'database': 'test'
        }
        
        final_df = final_df.astype({'views': 'int64',
                                    'likes': 'int64',
                                    'messages_sent': 'int64',
                                    'users_sent': 'int64',
                                    'messages_received': 'int64',
                                    'users_received': 'int64'})
        
        query = '''
                CREATE TABLE IF NOT EXISTS test.lrusinova
                (event_date Date,
                 views Int64,
                 likes Int64,
                 messages_sent Int64,
                 users_sent Int64,
                 messages_received Int64,
                 users_received Int64,
                 dimension String,
                 dimension_value String
                ) ENGINE = Log() '''
        
        pandahouse.execute(query=query, connection=connection_test)
        pandahouse.to_clickhouse(df=final_df, table='lrusinova', index=False, connection=connection_test)
    

    df_feed_cube = extract_feed_actions()
    df_messages_cube = extract_message_actions()
    df_merged = merge_all(df_feed_cube, df_messages_cube)
    
    df_gender = transform_gender(df_merged)
    df_age = transform_age(df_merged)
    df_os = transform_os(df_merged)
    final_df = transform_final_df(df_gender, df_os, df_age)
    
    load(final_df)

dag_rusinova_6_final = dag_rusinova_6_final()