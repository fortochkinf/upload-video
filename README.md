Требования:
Тестировалось на python 3.8 и 3.10
На каждый youtube аккаунт завести соответствующий google account
Для работы загрузки обложек в аккаунте youtube должен быть подтвержден телефон

В консоли управления google:
Подключить youtube data api v3
создать авторизацию OAuth2 и выгрузить файл ключа client_secret*.json, указать в конфиге для канала
при первом запуске откроется окно браузера где нужно будет предоставить права доступа.
потом обновление авторизации будет происходить по refresh токену


Запуск на ubuntu:
apt install python3.8 python3.8-venv

python3.8 -m venv venv
. ./venv/bin/activate
pip install -r requirements.txt

python upload-video.py


