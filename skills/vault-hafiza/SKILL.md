---
name: vault-hafiza
description: Kullanıcının kalıcı hafızası olan, Claude Code ve Codex oturumlarının damıtıldığı ve git ile makineler arasında eşitlenen Obsidian vault'unu okur ve yazar. Oturumda üretilen notları, kararları ve öğrenimleri vault'a kaydeder; geçmiş çalışmayı, proje durumunu ve süre dökümünü vault'tan cevaplar; süre panosunu açar; yeni kaynakları işler; vault sağlık kontrolü yapar; sistemi kurar, günceller ya da kaldırır. Tetikleyiciler; "obsidiene geçir", "obsidian'a aktar", "vault'a yaz", "hafızaya kaydet", "bunu not al", "nerede kalmıştık", "geçen hafta X projesinde ne yaptım", "X projesinde ne kadar çalıştım", "panoyu aç", "bu kaynağı işle", "vault lint", "hafıza neden güncellenmedi", "vault hafıza kurulumu", "hafızayı güncelle".
---

# Vault hafıza

Kullanıcının kalıcı hafızası bir Obsidian vault'udur ve git ile birden fazla makine arasında eşitlenir.

- Araç: `~/.vault-memory/bin/vm` (aşağıda kısaca `vm`). Yoksa sistem kurulu değildir: **Kurulum** bölümüne geç.
- Vault yolu: `~/.vault-memory/config.json` dosyasındaki `vault` alanı.
- Kurallar: vault kökündeki `CLAUDE.md`. Vault'a bir şey yazmadan önce onu oku. Bu skill ile çelişirse `CLAUDE.md` kazanır.

Oturumlar bittikten yaklaşık 20 dakika sonra arka plan işçisi tarafından kendiliğinden işlenir. Bu skill, kullanıcı beklemek istemediğinde, hafızadan bir şey sorduğunda ya da sistemi kurmak veya değiştirmek istediğinde kullanılır.

## Hangi işlem

| Kullanıcının isteği | Bölüm |
|---|---|
| "Obsidiene geçir", "bu oturumu kaydet" | Oturumu şimdi işle |
| "Şunu not al: …" gibi belirli bir içerik | Belirli bir notu yaz |
| "Nerede kalmıştık", "X'te ne yapmıştık" | Hafızadan cevapla |
| "Ne kadar çalıştım", "geçen hafta ne yaptım" | Süre dökümü |
| "Panoyu aç" | Pano |
| "Bu yazıyı / PDF'i işle" | Kaynak işle |
| "Vault'u kontrol et", "lint" | Sağlık kontrolü |
| "Hafıza güncellenmiyor" | Sorun giderme |
| "Kur", "bu makineyi ekle", "güncelle", "kaldır" | Kurulum, Güncelleme, Kaldırma |

## Oturumu şimdi işle

1. Oturum kimliğini bul. Oturum başında bağlama eklenen `<vault-hafiza>` bloğunda "Oturum kimliği" satırı vardır.
2. İşçiyi bu oturum için çalıştır. Komut bir iki dakika sürebilir; en az 5 dakikalık zaman aşımıyla çalıştır:

   ```bash
   ~/.vault-memory/bin/vm worker --session <oturum kimliği>
   ```

   Kimlik bulunamazsa `vm worker --now` bekleyen bütün oturumları işler.
3. Ne yazıldığını kontrol et ve kullanıcıya raporla:

   ```bash
   git -C "<vault yolu>" log -3 --stat --format='%h %s'
   ```

   Rapor kısa olsun: hangi sayfalar oluştu ya da güncellendi (vault-göreli yol), push durumu.

Komut oturumun o ana kadarki kısmını işler. Oturum devam ederse kalan kısım sonra ayrı bir bölüm olarak işlenir; tekrar çalıştırmak aynı kısmı iki kez yazmaz.

## Belirli bir notu yaz

Kullanıcı kaydedilecek içeriği açıkça söylediyse işçiyi bekleme, doğrudan yaz:

1. `CLAUDE.md`'ye göre doğru yeri seç. Önce `index.md`'de ve ilgili klasörde aynı konuda sayfa var mı bak; varsa onu güncelle.
2. Yeri belli değilse `00-Inbox/YYYY-MM-DD <konu>.md` olarak yaz.
3. Frontmatter zorunlu. Sır (anahtar, token, şifre) yazma.
4. `vm sync` çalıştır ve sonucu raporla.

## Hafızadan cevapla

1. `index.md`'yi oku ve ilgili sayfaları bul.
2. Proje sorusuysa önce proje sayfasını (`02-Projects/PRJ-<ad>/PRJ-<ad>.md`) oku; ayrıntı gerekiyorsa o projenin `sessions/` dosyalarını ve `log.md`'de `| PRJ-<ad> |` geçen satırları oku.
3. Cevabı vault-göreli sayfa yollarıyla ver. Vault'ta olmayan bilgiyi uydurma; yoksa "kayıt yok" de.
4. Cevap kalıcı değer taşıyorsa (karşılaştırma, analiz) `04-Resources/Syntheses/` altına sayfa olarak kaydetmeyi öner.

## Süre dökümü

Süreyi kafadan hesaplama, raporu çalıştır:

```bash
~/.vault-memory/bin/vm report --project <ad> --week last --detail
```

- `--week this|last`, ya da `--from YYYY-MM-DD --to YYYY-MM-DD`, ya da `--days 7`.
- `--project` verilmezse bütün projeler listelenir. Proje adı kısmi eşleşir.
- `--detail` her gün için oturum başlıklarını da yazar. `--json` makine okunur çıktı verir.

Kullanıcıya şunu belirt: süre, ajanla etkin çalışma süresidir; ajansız geçen zamanı ve uzun boşlukları içermez, aynı anda açık oturumlar ayrı ayrı sayılır. Grafik ve filtre için panoyu öner.

## Pano

```bash
~/.vault-memory/bin/vm dashboard            # http://127.0.0.1:4747, tarayıcıyı açar
~/.vault-memory/bin/vm dashboard --port 4800 --no-open
```

Durdurulana kadar ön planda çalışır; kullanıcı için başlatırken arka planda çalıştır ve adresi ver. Sayfa vault'u canlı okur, İngilizce/Türkçe seçeneği vardır. Bilgisayar açılınca kendiliğinden başlaması için: `vm install --dashboard`.

## Kaynak işle

`CLAUDE.md`'deki "Kaynak işleme" adımlarını uygula: ham dosyayı değiştirmeden oku, `04-Resources/Sources/` altına özet sayfası yaz, kaynağın değdiği sayfaları güncelle, `vm sync` çalıştır. Hangi sayfalara dokunduğunu raporla. `vm ingest` aynı işi gelen kutusu klasörlerindeki bütün yeni dosyalar için yapar.

## Sağlık kontrolü

1. `vm lint` çalıştır; rapor `99-Meta/Lint/YYYY-MM-DD.md` dosyasına yazılır.
2. Raporu oku. "Anlam denetimi" bölümünü doldur: çelişen ya da eskimiş iddialar, birleştirilmesi gereken sayfalar, sık geçtiği halde sayfası olmayan kavramlar.
3. Güvenli düzeltmeleri yap (eksik frontmatter, kopuk link). Sayfa silme, dosya taşıma; bunları raporda öner.
4. `vm sync` çalıştır ve bulguları özetle.

## Sorun giderme

```bash
~/.vault-memory/bin/vm status
```

- Bekleyen oturumları, son işçi kayıtlarını ve varsa uyarıyı gösterir. Ayrıntılı kayıt: `~/.vault-memory/logs/worker.log`.
- Sır benzeri bir değer yüzünden commit durduruldu uyarısı varsa: vault'ta `git status` ile değişen dosyaları bul, sır değerini sil, sonra `vm sync` çalıştır.
- Eşitleme çakışması uyarısı varsa: vault klasöründe `git pull --rebase` çalıştır, çakışan dosyayı kullanıcıyla birlikte çöz, sonra `vm sync`.
- Hook'lar eksikse ya da makine yeni kuruluyorsa: `<vault>/99-Meta/System/bin/vm install --machine <ad>`.

## Kurulum

Yalnızca `~/.vault-memory/bin/vm` yoksa ya da kullanıcı kurulum isterse.

1. Kullanıcıya tek mesajda sor:
   - Vault nerede dursun (varsayılan `~/Vault`; yeni ve boş bir klasör en güvenlisi).
   - Vault sayfalarının dili: `en` ya da `tr`.
   - Bir git uzak deposuyla eşitlensin mi? Evet ise boş ve **özel (private)** bir deponun adresini iste; vault çalışmalarının özetini taşır.
   - 5 dakikada bir çalışan arka plan zamanlayıcısı kurulsun mu (önerilir; yoksa oturumlar yalnızca bir hook tetiklendiğinde işlenir).
2. Kaynağı al ya da güncelle:

   ```bash
   if [ -d ~/.vault-memory/src/.git ]; then git -C ~/.vault-memory/src pull --ff-only; \
   else git clone https://github.com/yusufkaran/obsidian-agent-memory ~/.vault-memory/src; fi
   ```

3. Kur:

   ```bash
   ~/.vault-memory/src/install.sh --vault <yol> --lang <en|tr> [--remote <git adresi>] [--timer]
   ```

   Bu skill bir plugin'den yüklendiyse (temel klasörü `~/.claude/plugins/` altındaysa) skill iki kez kurulmasın diye `--no-skill` ekle.
4. `vm status` çalıştır ve raporla: vault yolu, makine adı, hook'lar, zamanlayıcı. Kullanıcıya şunu söyle: oturumlar boşta kaldıktan yaklaşık 20 dakika sonra işlenir; kurulumdan önceki oturumlar `vm backfill --days N` çalıştırılmadıkça vault'a girmez (oturum başına bir LLM çağrısı).

**Başka bir makine** (vault zaten bir git uzak deposunda):

```bash
git clone <uzak depo adresi> ~/Vault
~/Vault/99-Meta/System/bin/vm install --machine <ad> --timer
```

Kapağı sık kapanan dizüstünde `vm config capture true`, sırları temizlenmiş özetleri uzak depoya gönderir; hep açık makinede `vm config process_remote true` bu özetleri işler.

## Güncelleme

```bash
git -C ~/.vault-memory/src pull --ff-only
~/.vault-memory/src/install.sh --vault <vault yolu>
~/.vault-memory/bin/vm sync
```

Kurulum betiği yeni betikleri, panoyu ve skill'i vault'a kopyalar; vault'un dilini ve ayarlarını korur. `vm sync` bunları gönderir; diğer makineler bir sonraki pull'da yeni sürümü çalıştırır.

## Kaldırma

```bash
~/.vault-memory/bin/vm uninstall              # skill kalsın istersen --keep-skill
```

Bu makineden hook'ları, zamanlayıcıyı, pano servisini ve kurulu skill'i kaldırır. Vault'a ve git geçmişine dokunmaz.
