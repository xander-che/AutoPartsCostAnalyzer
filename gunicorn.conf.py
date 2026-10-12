import os


bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Фоновые задачи поиска хранятся в памяти процесса, поэтому нужен один
# процесс с несколькими потоками. Иначе опрос статуса может попасть в другой процесс.
workers = 1
threads = int(os.getenv('WEB_THREADS', '4'))
worker_class = 'gthread'
timeout = int(os.getenv('WEB_TIMEOUT', '120'))
graceful_timeout = 30
keepalive = 5
accesslog = '-'
errorlog = '-'
capture_output = True
