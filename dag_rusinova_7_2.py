import telegram
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import io
import pandas as pd
import pandahouse
import requests
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

def ch_get_df(query='Select 1', host='https://clickhouse.lab.karpov.courses', user='student', password='dpo_python_2020'):
    r = requests.post(host, data=query.encode("utf-8"), auth=(user, password), verify=False)
    result = pd.read_csv(io.StringIO(r.text), sep='\t')
    return result

my_token = '5587138258:AAFL9OAnYEhPzE2xFaJnRtb9rpTYogMqZEw'

bot = telegram.Bot(token=my_token)

default_args = {
    'owner': 'l-rusinova-9',
    'depends_on_past': False,
    'retries': 10,
    'retry_delay': timedelta(minutes=1),
    'start_date': datetime(2022, 7, 20)
}

schedule_interval = '0 11 * * *'

personal_chat_id = 976168502
group_chat_id = -770113521



@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def dag_rusinova_7_2():
    
    
    
    @task
    def extract_week_data():
        
        query = '''

        SELECT
            t1.day, t1.month, t1.user_id, t1.os, t1.gender, t1.country, t1.source,
            t1.views, t1.likes, t1. CTR, t1.views_per_user, t1.likes_per_user,
            t2.messages, t2.messages_per_user

        FROM

            (
            SELECT 
                toDate(toStartOfDay(time)) AS day,
                toDate(toStartOfMonth(day)) AS month,
                user_id,
                os,
                gender,
                country,
                source,
                countIf(post_id, action='view') AS views,
                countIf(post_id, action='like') AS likes,
                round(likes / views, 2) as CTR,
                round(countIf(action='view') / countDistinctIf(user_id, action='view'), 2) AS views_per_user,
                round(countIf(action='like') / countDistinctIf(user_id, action='like'), 2) AS likes_per_user 

            FROM 
                simulator_20220720.feed_actions

            WHERE
                toDate(time) between today()-7 and today()-1

            GROUP BY
                day, user_id, os, gender, country, source
            ORDER BY
                day

            ) AS t1

            LEFT JOIN

            (
            SELECT 
                toDate(toStartOfDay(time)) AS day,
                toDate(toStartOfMonth(day)) AS month,
                user_id,
                os,
                gender,
                country,
                source,
                count(user_id) AS messages,
                round(count(user_id) / countDistinct(user_id), 2) AS messages_per_user

            FROM 
                simulator_20220720.message_actions

            WHERE
                toDate(time) between today()-7 and today()-1

            GROUP BY
                day, user_id, os, gender, country, source
            ORDER BY
                day

            ) AS t2

            ON
                t1.user_id = t2.user_id AND t1.day = t2.day

        format TSVWithNames
        '''

        all_df = ch_get_df(query=query)
        return all_df

    
    
    @task
    def send_yesterday_totals(all_df, chat_id):

        df_yesterday = all_df[ all_df['day'] == max(all_df['day']) ]

        df_yesterday_grouped = df_yesterday.groupby('day', as_index=False)\
                                            .agg({'user_id' : 'count', 
                                                  'views' : 'sum',
                                                  'likes' : 'sum', 
                                                  'CTR' : 'mean',
                                                  'views_per_user' : 'mean',
                                                  'likes_per_user' : 'mean',
                                                  'messages': 'sum',
                                                  'messages_per_user': 'mean'
                                                 })

        dau = df_yesterday_grouped.iloc[0]['user_id']
        views = df_yesterday_grouped.iloc[0]['views']
        likes = df_yesterday_grouped.iloc[0]['likes']
        ctr = df_yesterday_grouped.iloc[0]['CTR']
        views_per_user = df_yesterday_grouped.iloc[0]['views_per_user']
        likes_per_user = df_yesterday_grouped.iloc[0]['likes_per_user']
        messages = df_yesterday_grouped.iloc[0]['messages']
        messages_per_user = df_yesterday_grouped.iloc[0]['messages_per_user']

        users_android = len(df_yesterday[ df_yesterday['os'] == 'Android'])
        users_ios = len(df_yesterday[ df_yesterday['os'] == 'iOS'])
        users_organic = len(df_yesterday[ df_yesterday['source'] == 'organic'])
        users_ads = len(df_yesterday[ df_yesterday['source'] == 'ads'])
        users_active = len(df_yesterday[ df_yesterday['messages'] > 0])
        users_read_only = len(df_yesterday[ df_yesterday['messages'] == 0])

        msg = "-" * 20 + '\n' \
        + f'\nОбщая статистика за вчера:\n\n' \
        + f'DAU: {dau}\n' \
        + f'Просмотры: {views}\n' \
        + f'Лайки: {likes}\n' \
        + f'CTR: {ctr:.2f}\n' \
        + f'Сообщения: {messages}\n' \
        + f'\nПросмотры на 1 пользователя: {views_per_user:.2f}\n' \
        + f'Лайки на 1 пользователя: {likes_per_user:.2f}\n' \
        + f'Сообщения на 1 пользователя: {messages_per_user:.2f}\n' \
        + '\n' + "-" * 20 + '\n' \
        + f'\nСостав пользователей:\n' \
        + f'\nAndroid: {users_android}\n' \
        + f'iOS: {users_ios}\n' \
        + f'\nОрганические каналы: {users_organic}\n' \
        + f'Рекламные каналы: {users_ads}\n' \
        + f'\nЧитают ленту и пишут сообщения: {users_active}\n' \
        + f'Только пишут сообщения: {users_read_only}\n' \
        + '\n' + "-" * 20 + '\n'

        bot.sendMessage(chat_id=chat_id, text=msg)

            

    @task
    def send_week_totals(all_df, chat_id):

        # Считаем суммы / медианы показателей за каждый день

        all_df_grouped = all_df.groupby('day', as_index=False)\
                            .agg({'user_id' : 'count', 
                                'views' : 'sum',
                                'likes' : 'sum', 
                                'CTR' : 'mean',
                                'views_per_user' : 'mean',
                                'likes_per_user' : 'mean',
                                'messages': 'sum',
                                'messages_per_user': 'mean'
                             })

        fig, axes = plt.subplots(2, 3, figsize=(20, 14))

        fig.suptitle('Динамика показателей за последние 7 дней', fontsize=30)

        sns.lineplot(ax = axes[0, 0], data = all_df_grouped, x = 'day', y = 'user_id')
        axes[0, 0].set_title('DAU')
        axes[0, 0].grid()

        sns.lineplot(ax = axes[0, 1], data = all_df_grouped, x = 'day', y = 'views')
        axes[0, 1].set_title('Просмотры')
        axes[0, 1].grid()

        sns.lineplot(ax = axes[0, 2], data = all_df_grouped, x = 'day', y = 'likes')
        axes[0, 2].set_title('Лайки')
        axes[0, 2].grid()

        sns.lineplot(ax = axes[1, 0], data = all_df_grouped, x = 'day', y = 'CTR')
        axes[1, 0].set_title('CTR')
        axes[1, 0].grid()

        sns.lineplot(ax = axes[1, 1], data = all_df_grouped, x = 'day', y = 'views_per_user')
        axes[1, 1].set_title('Views per user')
        axes[1, 1].grid()

        sns.lineplot(ax = axes[1, 2], data = all_df_grouped, x = 'day', y = 'likes_per_user')
        axes[1, 2].set_title('Likes per user')
        axes[1, 2].grid()

        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'Stat.png'
        plt.close()

        bot.sendPhoto(chat_id=chat_id, photo=plot_object)
            

    
    data = extract_week_data()
    send_yesterday_totals(data, group_chat_id)
    send_week_totals(data, group_chat_id)
    
    
dag_rusinova_7_2 = dag_rusinova_7_2()