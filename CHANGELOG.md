# Değişiklik günlüğü

Her sürümdeki önemli değişiklikler burada tutulur. Sürüm numarası `akis/__init__.py` içindedir.

## 0.3.7

### Güvenlik
- **Proje dosyası doğrulaması:** `.akis.json` içindeki zaman çizelgesi (fps, kare konumları, klip alanları, ses düzeyi, işaretler, keyframe'ler) ile `state`, `publish` ve `ai_prompt` alanları tip ve aralık olarak doğrulanıyor. Hatalı veya kötü amaçlı değerler (ör. FFmpeg filtre grafiğine metin enjekte etmeye çalışan bir fps değeri) projeyi açmadan reddediliyor. 20 MB üzeri proje dosyaları kabul edilmiyor.
- **FFmpeg girdi sıkılaştırması:** Tüm medya girdileri yalnızca yerel dosya protokolüyle ve desteklenen kapsayıcı formatlarla (MP4/MOV/M4V/M4A, MKV/WebM, AVI, MP3, WAV) açılıyor. Böylece ağ/pipe adresleri ve diskteki başka dosyaları gizlice içeri çekebilen concat/HLS gibi çalma listesi formatları engelleniyor.
- **Yerel Whisper:** Altyazı için kaynak dosya doğrudan açılmıyor; ses önce korumalı FFmpeg ile geçici WAV dosyasına çıkarılıyor.

### Derleme ve yayın
- Sürüm numarasının tek kaynağı `akis/__init__.py`. Güncelleme denetimi, kurucu (`/DAppVersion`) ve GitHub sürüm etiketi bu değerden üretiliyor; artık üç ayrı yerde elle değiştirmek gerekmiyor.
- Sürüm artırılmadan `main`'e gönderim yapılırsa CI, kullanıcılara güncelleme gitmeyeceğine dair görünür bir uyarı veriyor.
- GitHub Actions eylemleri commit SHA'larına, kurucuya giren FFmpeg Chocolatey sürümüne (9.0.2) sabitlendi. FFmpeg ve kurucunun SHA-256 özetleri çalıştırma özetine, kurucunun özeti sürüm notlarına yazılıyor.
- CI artık `main`'e açılan pull request'lerde de çalışıyor (yayın yapmadan). Checkout adımı kimlik bilgisi saklamıyor; aynı dal için eşzamanlı yayın derlemesi engelleniyor.

### Belgeler
- README'deki indirme bağlantısı her zaman en son sürümü gösteriyor; eski `experimental/timeline-render` adımı kaldırıldı, SmartScreen uyarısı ve yayın süreci anlatıldı.
