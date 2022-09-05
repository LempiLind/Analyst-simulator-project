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

query_yesterday = '''SELECT

                    countDistinct(user_id) AS DAU,
                    countIf(action='view') AS views,
                    countIf(action='like') AS likes,
                    likes/views AS CTR

                    FROM simulator_20220720.feed_actions

                    WHERE toDate(time) = yesterday()
                    
                    format TSVWithNames
                    '''

query_week = '''SELECT

                toDate(time) AS event_date,
                countDistinct(user_id) AS DAU,
                countIf(action='view') AS views,
                countIf(action='like') AS likes,
                likes/views AS CTR
                
                FROM simulator_20220720.feed_actions
                
                WHERE toDate(time) BETWEEN yesterday()-7 and yesterday()
                
                GROUP BY event_date
                
                format TSVWithNames
                '''

personal_chat_id = 976168502
group_chat_id = -770113521


@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def dag_rusinova_7_1():
    
    
    @task()
    def extract_data(query):
        df = ch_get_df(query=query)
        return df
    
    
    @task()
    def send_message_yesterday(data, chat_id):
        dau = data['DAU'].sum()
        views = data['views'].sum()
        likes = data['likes'].sum()
        ctr = data['CTR'].sum()

        msg = '-' * 20 + '\n\n' + f'Статистика ленты новостей за вчера:\n\nDAU: {dau}\nПросмотры: {views}\nЛайки: {likes}\nCTR: {ctr:.2f}\n' + '-' * 20 + '\n'

        bot.sendMessage(chat_id=chat_id, text=msg)
    
    
    @task
    def send_photo_week(data, chat_id):
        fig, axes = plt.subplots(2, 2, figsize=(20, 14))

        fig.suptitle('Динамика показателей за последние 7 дней', fontsize=30)

        sns.lineplot(ax = axes[0, 0], data = data, x = 'event_date', y = 'DAU')
        axes[0, 0].set_title('DAU')
        axes[0, 0].grid()

        sns.lineplot(ax = axes[0, 1], data = data, x = 'event_date', y = 'CTR')
        axes[0, 1].set_title('CTR')
        axes[0, 1].grid()

        sns.lineplot(ax = axes[1, 0], data = data, x = 'event_date', y = 'views')
        axes[1, 0].set_title('Просмотры')
        axes[1, 0].grid()

        sns.lineplot(ax = axes[1, 1], data = data, x = 'event_date', y = 'likes')
        axes[1, 1].set_title('Лайки')
        axes[1, 1].grid()

        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'Stat.png'
        plt.close()

        bot.sendPhoto(chat_id=chat_id, photo=plot_object)
    
    
    
    df_yesterday = extract_data(query_yesterday)
    df_week = extract_data(query_week)
    send_message_yesterday(df_yesterday, group_chat_id)
    send_photo_week(df_week, group_chat_id)
    
dag_rusinova_7_1 = dag_rusinova_7_1()