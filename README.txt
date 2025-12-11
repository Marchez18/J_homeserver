Python telgram bot shopping and Idea list


ENV ACTIVATION
python3 -m venv venv
source venv/bin/activate

python3 -m venv ~/J_homeserver
source ~/J_homeserver/bin/activate

ENV STANDALONE
~/python/bin/python3.11 -m venv venv
source venv/bin/activate




✅ 2. Parar el bot
sudo docker stop jbot-container

✅ 3. Arrancar el bot
sudo docker start jbot-container

✅ 4. Reiniciar el bot
sudo docker restart jbot-container


✅ 5. Actualizar código con git pull y reconstruir la imagen

En tu carpeta del proyecto (~/J_homeserver):

git pull
sudo docker build -t jbot .
sudo docker stop jbot-container
sudo docker rm jbot-container
sudo docker run -d --name jbot-container jbot