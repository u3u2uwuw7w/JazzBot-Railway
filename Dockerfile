# 1. Official Python Image
FROM python:3.10-slim

# 2. System tools aur downloader install karo
RUN apt-get update && apt-get install -y aria2 curl

# 3. Folder set karo
WORKDIR /app
COPY . /app

# 4. Requirements aur Browser install karo
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps

# 5. Bot Start karo
CMD ["python", "bot.py"]
