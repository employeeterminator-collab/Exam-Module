# 使用官方輕量級 Python 3.11 映像檔
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 先複製 requirements.txt 並安裝相依套件（利用 Docker 快取加速建置）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案內的所有檔案（包含 cert_app.py、字型檔、PDF 範本與圖片）
COPY . .

# 暴露 Cloud Run 預設接收的連接埠
EXPOSE 8080

# 啟動 Streamlit 應用程式，並繫結至 Cloud Run 的動態 PORT
CMD streamlit run cert_app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true