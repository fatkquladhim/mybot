# 🚀 Panduan Deploy FatQul AI Trader ke VPS IDCloudHost

Dokumen ini berisi panduan langkah-demi-langkah untuk mendeploy bot trading Anda dari komputer lokal ke VPS IDCloudHost menggunakan Docker.

---

## 💻 Langkah 1: Persiapan di Komputer Lokal

Cara paling mudah dan rapi untuk memindahkan proyek ini adalah menggunakan **Git (GitHub / GitLab)**. 

### A. Pindahkan file sensitif ke `.gitignore`
Pastikan file `.env` dan file database `.sqlite` **TIDAK** ikut ter-upload ke Git demi alasan keamanan API Key Anda.

File `.gitignore` di folder `freqtrade_repo` Anda seharusnya sudah memiliki baris ini secara default:
```text
.env
*.sqlite
user_data/logs/*
```

### B. Push ke Private Repository (GitHub)
Jalankan perintah ini di Terminal lokal Anda di dalam folder `freqtrade_repo`:
```bash
# Inisialisasi git jika belum
git init
git add .
git commit -m "feat: FatQul AI Trader MVP integration"

# Buat repository baru di GitHub (set as PRIVATE!) lalu hubungkan:
git remote add origin git@github.com:USERNAME/NAMA_REPO_ANDA.git
git branch -M main
git push -u origin main
```

*(Catatan: Jika Anda tidak ingin menggunakan Git, Anda bisa mengompres folder `freqtrade_repo` menjadi `.zip` (tanpa folder `.git`) lalu meng-uploadnya menggunakan SCP atau SFTP seperti FileZilla).*

---

## ☁️ Langkah 2: Setup di VPS IDCloudHost

Masuk ke VPS IDCloudHost Anda menggunakan SSH:
```bash
ssh root@IP_ADDRESS_VPS_ANDA
```

### A. Update VPS & Install Docker + Git
Jalankan perintah ini di VPS Anda (asumsi OS: **Ubuntu 20.04/22.04 LTS**):
```bash
# Update package manager
sudo apt update && sudo apt upgrade -y

# Install git & curl
sudo apt install git curl -y

# Install Docker Engine
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose (V2)
sudo apt install docker-compose-plugin -y

# Pastikan Docker sudah berjalan
sudo systemctl enable docker
sudo systemctl start docker
```

---

## 🚚 Langkah 3: Menarik Proyek & Konfigurasi di VPS

### A. Clone Repo di VPS
```bash
# Clone repository private Anda
git clone git@github.com:USERNAME/NAMA_REPO_ANDA.git fatqul-bot
cd fatqul-bot
```

### B. Buat & Konfigurasi File `.env` di VPS
Karena file `.env` tidak kita upload ke Git, kita harus membuatnya manual di VPS:
```bash
nano .env
```
Copy-paste template berikut dan isi dengan data asli Anda:
```env
# Freqtrade Indodax API Keys
INDODAX_API_KEY=isi_key_indodax_asli_disini
INDODAX_API_SECRET=isi_secret_indodax_asli_disini

# Sumopod AI Engine
SUMOPOD_API_KEY=sk-B9uHqDSDU3U0GCA03LiK4w
SUMOPOD_BASE_URL=https://ai.sumopod.com/v1
SUMOPOD_MODEL=gemini/gemini-2.5-flash-lite

# WhatsApp / Evolution API Config (Kosongkan jika belum ada server Evolution)
TARGET_PHONE=62812xxxxxxx
EVOLUTION_API_URL=http://your-evolution-api-url:8080
EVOLUTION_API_KEY=your_evolution_api_key
INSTANCE_NAME=FatQulBot
```
Tekan `CTRL + O` lalu `ENTER` untuk menyimpan, dan `CTRL + X` untuk keluar.

---

## ⚡ Langkah 4: Jalankan Bot di VPS!

Jalankan perintah berikut untuk menginisialisasi database sqlite, mem-build container dashboard, dan menjalankan bot di background:

```bash
# Buat folder log & database kosong agar permission docker aman
mkdir -p user_data/logs
touch user_data/tradesv3.sqlite

# Jalankan docker compose
sudo docker compose up -d --build
```

### Memeriksa Status Bot
*   **Melihat log bot secara real-time:**
    ```bash
    sudo docker compose logs -f freqtrade
    ```
*   **Melihat status semua container:**
    ```bash
    sudo docker compose ps
    ```
*   **Menghentikan bot:**
    ```bash
    sudo docker compose down
    ```

---

## 🔐 Keamanan Tambahan (Sangat Direkomendasikan)

1.  **Akses Dashboard Streamlit (`http://IP_VPS:8501`)**:
    Port `8501` saat ini terbuka. Jika VPS Anda memiliki public IP, siapa saja bisa membuka dashboard Anda. 
    *Saran:* Ganti kredensial login di file `user_data/config.json` bagian `api_server` dan amankan port VPS Anda menggunakan firewall UFW untuk hanya membolehkan IP Anda yang mengakses port `8501` dan `8080`.
    ```bash
    sudo ufw allow 22/tcp
    sudo ufw allow from IP_KLAIM_ANDA to any port 8501
    sudo ufw enable
    ```
