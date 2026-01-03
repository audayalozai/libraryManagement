# استخدام نسخة بايثون خفيفة ومستقرة
FROM python:3.11-slim

# تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# تثبيت التبعيات الضرورية للنظام (إذا لزم الأمر)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# نسخ ملف المكتبات المطلوبة أولاً للاستفادة من الـ Cache
COPY requirements.txt .

# تثبيت مكتبات بايثون
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع إلى الحاوية
COPY . .

# تشغيل البوت
CMD ["python", "main.py"]
