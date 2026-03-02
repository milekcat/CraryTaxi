# Используем легкую версию Python
FROM python:3.11-slim

# Устанавливаем рабочую папку внутри сервера
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все остальные файлы (main.py, index.html)
COPY . .

# Говорим Амвере, что наш порт - 8080
EXPOSE 8080

# Команда запуска
CMD ["python", "main.py"]
