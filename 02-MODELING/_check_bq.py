from google.cloud import bigquery
c = bigquery.Client(project='nfl-model-471509')
c.query('SELECT 1').result()
print('BigQuery OK')
