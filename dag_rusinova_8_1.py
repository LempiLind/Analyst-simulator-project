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

schedule_interval = '*/15 * * * *'

personal_chat_id = 976168502
group_chat_id = -788021703

@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def dag_rusinova_8_1():

    @task
    def extract_feed():
        
        query_feed = '''

            SELECT
                toStartOfFifteenMinutes(time) AS timestamp,
                toDate(toStartOfDay(time)) AS day,
                formatDateTime(timestamp, '%R') AS hm,
                countDistinct(user_id) AS feed_users,
                countIf(user_id, action='view') AS views,
                countIf(user_id, action='like') AS likes
            FROM
                simulator_20220720.feed_actions
            WHERE
                toDate(time) >= today()-1 AND timestamp < toStartOfFifteenMinutes(now())
            GROUP BY
                timestamp, day, hm
            ORDER BY
                timestamp, day, hm

            format TSVWithNames

            '''
        
        feed_df = ch_get_df(query=query_feed)
        return feed_df
    
    
    @task
    def extract_messages():
        query_messages = '''

            SELECT 
                toStartOfFifteenMinutes(time) AS timestamp,
                toDate(toStartOfDay(time)) AS day,
                formatDateTime(timestamp, '%R') AS hm,
                countDistinct(user_id) AS message_users,
                count(user_id) AS messages
            FROM 
                simulator_20220720.message_actions
            WHERE
                toDate(time) >= today()-1 AND timestamp < toStartOfFifteenMinutes(now())
            GROUP BY
                timestamp, day, hm
            ORDER BY
                timestamp, day, hm

            format TSVWithNames

            '''
        
        message_df = ch_get_df(query=query_messages)
        return message_df
    

    def check_anomaly(df, metric, a=4, n=7):

        df['q25'] = df[metric].shift(1).rolling(n).quantile(0.25)
        df['q75'] = df[metric].shift(1).rolling(n).quantile(0.75)
        df['iqr'] = df['q75'] - df['q25']
        df['up'] = df['q75'] + a*df['iqr']
        df['down'] = df['q25'] - a*df['iqr']

        df['up'] = df['up'].rolling(n, center = True, min_periods = 1).mean()
        df['down'] = df['down'].rolling(n, center = True, min_periods = 1).mean()

        if df[metric].iloc[-1] < df['down'].iloc[-1] or df[metric].iloc[-1] > df['up'].iloc[-1]:
            is_alert = 1
        else:
            is_alert = 0

        return is_alert, df

    @task
    def run_alerts(df, metrics_list, chat_id):

        my_token = '5587138258:AAFL9OAnYEhPzE2xFaJnRtb9rpTYogMqZEw'

        bot = telegram.Bot(token=my_token)

        for metric in metrics_list:
            tmp_df = df[['timestamp', 'day', 'hm', metric]].copy()
            is_alert, tmp_df = check_anomaly(tmp_df, metric)

            if is_alert == 1:
                msg = "-" * 20 + '\n\n'
                msg += '''Метрика {metric}\nтекущее значение {current_val:.2f} \nотклонение от предыдущего значения {last_val_diff:.2%}\n'''.format(metric = metric, current_val = tmp_df[metric].iloc[-1], last_val_diff = abs(tmp_df[metric].iloc[-1] / tmp_df[metric].iloc[-2]))
                
                sns.set(rc={'figure.figsize': (16, 10)})
                plt.tight_layout()

                ax = sns.lineplot(x = tmp_df['timestamp'], y = tmp_df[metric], label = 'metric')
                ax = sns.lineplot(x = tmp_df['timestamp'], y = tmp_df['up'], label = 'up')
                ax = sns.lineplot(x = tmp_df['timestamp'], y = tmp_df['down'], label = 'down')

                for ind, label in enumerate(ax.get_xticklabels()):
                    if ind % 30 == 0:
                        label.set_visible(True)
                        label.set_rotation(30)
                    else:
                        label.set_visible(False)

                ax.set(xlabel = 'time')
                ax.set(xlabel = metric)
                ax.set_title(metric)
                ax.set(ylim=(0, None))

                plot_object = io.BytesIO()
                plt.savefig(plot_object)
                plot_object.seek(0)
                plot_object.name = '{0}.png'.format('metric')
                plt.close()
                
                bot.sendMessage(chat_id=chat_id, text=msg)
                bot.sendPhoto(chat_id=chat_id, photo=plot_object)

                
                
    feed_df = extract_feed()
    metrics_list_feed = ['feed_users', 'views', 'likes']
    
    message_df = extract_messages()
    metrics_list_messages = ['message_users', 'messages']
    
    run_alerts(feed_df, metrics_list_feed, group_chat_id)
    run_alerts(message_df, metrics_list_messages, group_chat_id)
        
        
dag_rusinova_8_1 = dag_rusinova_8_1()