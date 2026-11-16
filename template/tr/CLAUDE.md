# Vault şeması

Bu vault, LLM'in yazıp güncel tuttuğu kalıcı bir hafızadır (Karpathy'nin "LLM Wiki" modeli).
Burada çalışan her ajan (Claude Code, Codex, arka plan işçisi) bu dosyadaki kurallara uyar.
Kullanıcı kaynak getirir ve soru sorar; yazım ve bakım işini ajan yapar.

## Katmanlar

| Katman | Yer | Kural |
|---|---|---|
| Ham | `05-Raw/`, proje içi `sessions/` | Yazıldıktan sonra değişmez; yalnızca sona eklenir |
| Wiki | `02-Projects/`, `04-Resources/` | Ajan yazar ve yerinde günceller |
| İnsan | `00-Inbox/`, `01-Journal/`, `03-Areas/` | Kullanıcı yazar; ajan yalnızca okur |
| Şema | bu dosya, `99-Meta/` | Kullanıcıyla birlikte değişir |

## Klasörler

```
index.md      katalog; betik üretir, elle düzenlenmez
log.md        zaman çizelgesi; betik sona ekler, elle düzenlenmez
00-Inbox/     kullanıcının attığı, henüz işlenmemiş her şey
01-Journal/   kullanıcının günlüğü (Daily/YYYY/YYYY-MM/YYYY-MM-DD.md)
02-Projects/PRJ-<ad>/
    PRJ-<ad>.md   projenin canlı sayfası
    sessions/     YYYY-MM-DD <ad> <makine>.md — o günün oturum kayıtları
    decisions/    ADR-NNNN <karar>.md
    meetings/     YYYY-MM-DD <başlık>.md
    notes/        çalışma notu, debug günlüğü, spec
03-Areas/     süregelen alanlar
04-Resources/
    Topics/     kavram ve öğrenim; başlık bir iddia cümlesidir
    Entities/   araç, servis, şirket, kişi
    Sources/    işlenen her ham kaynağın özet sayfası
    Syntheses/  sorulara verilen kalıcı cevaplar, karşılaştırmalar
    Snippets/   <dil — ne yapar>.md
05-Raw/
    clippings/  Web Clipper ile kaydedilen yazılar
    files/      PDF, doküman
    sessions/   bir projeye ait olmayan oturum kayıtları (YYYY/YYYY-MM/)
    assets/     görseller
99-Meta/
    Templates/  sayfa şablonları
    Bases/      tablo görünümleri
    Lint/       sağlık raporları
    System/     betikler, pano, skill, ayar (elle değiştirme)
```

## Frontmatter

Her sayfa YAML frontmatter ile başlar. Zorunlu alanlar: `type`, `title`, `description`, `date`.

```yaml
---
type: project | adr | meeting | note | topic | entity | source | synthesis | snippet | session
title: Sayfanın adı
description: Tek cümle; index.md bu satırdan üretilir, somut yaz
date: 2026-11-11        # oluşturma
updated: 2026-11-11     # son anlamlı değişiklik
project: "[[PRJ-ad]]"   # bir projeye aitse
tags: [etiket, etiket]
sources: ["[[2026-11-11 ad laptop]]"]   # iddianın dayandığı oturum ya da kaynak
---
```

Türe özel alanlar:

- `project`: `status` (aktif | beklemede | bitti), `repos` (bu projeye ait depoların listesi, ör. `github.com/sahip/depo`), `folders` (bu projeye ait klasör adları listesi). `repos` ve `folders` oturumları projeye eşlemek için kullanılır ve betik tarafından doldurulur; silme. Bir proje birden fazla depo içerebilir.
- `session`: `machine`, `minutes`, `sessions`, `tools`. Bu dört alanı betik yazar; ajan dokunmaz.
- `source`: `raw` (ham dosyanın vault-göreli yolu), `author`, `url`.
- `adr`: `status` (kabul | değişti | iptal).

Mevcut bir sayfayı düzenlerken var olan frontmatter alanlarını koru.

## Yazım kuralları

- Dil Türkçe. Kod, komut ve dosya yolları olduğu gibi kalır.
- Transkript değil damıtılmış özet yaz: ne yapıldı, neden, ne karar verildi, ne açık kaldı.
- Aynı konuda sayfa varsa yenisini açma, mevcut sayfayı güncelle. Önce `index.md`'ye, sonra ilgili klasöre bak.
- Wiki sayfaları yerinde güncellenir: eskiyen bilgiyi düzelt, üstüne tarihli ek yığma. Yeni bilgi eskisiyle çelişiyorsa eskisini sil ve `> [!note] 2026-11-11: önceki bilgi … idi` satırıyla not düş.
- İlk geçtiği yerde her şeyi `[[wikilink]]` ile bağla. Sayfası olmayan bir şeye link vermek serbesttir.
- Tarihler her yerde `YYYY-MM-DD`.
- Topic başlığı bir iddia cümlesidir: "Hook'lar ortam değişkenlerini üst süreçten devralır" gibi.
- Topic ve Entity sayfası yalnızca birden fazla projede işe yarayacak kalıcı bilgi için açılır. Emin değilsen açma; bilgiyi proje sayfasına yaz.
- Her wiki iddiası dayandığı oturumu ya da kaynağı `sources` alanında gösterir. Kaynakta olmayan bilgiyi uydurma; eksikse `TODO:` bırak.
- TODO'lar ait olduğu sayfaya `- [ ] iş` satırı olarak yazılır. Ayrı TODO dosyası açma.

### Proje sayfası

`PRJ-<ad>.md` şu bölümleri taşır ve hep güncel tutulur:

- `## Özet`: proje nedir, kimin için, hangi teknolojilerle.
- `## Durum`: şu an nerede. Üç beş cümle; her oturumdan sonra yeniden yazılır, uzatılmaz.
- `## Açık işler`: `- [ ]` satırları. Biten iş `- [x]` yapılır, bir sonraki güncellemede silinir.
- `## Kararlar`: tek satırlık kararlar ve ADR linkleri.
- `## Bilinmesi gerekenler`: kurulum, deploy, tuzaklar, önemli dosya yolları.
- `## Oturumlar`: tablo görünümü (`![[Oturumlar.base#Proje]]`); dokunma.

### Oturum kaydı

Oturum dosyasına yalnızca sona bölüm eklenir, önceki bölümler değişmez:

```markdown
## 14:32 — Kısa başlık (42 dk · claude-code)

**İstek:** kullanıcının istediği şey, bir iki cümle.
**Yapılanlar:** ne yapıldı; önemli komut ve dosyalar.
**Kararlar:** verilen kararlar ve gerekçeleri. Yoksa bu satırı yazma.
**Açık işler:** yarım kalan ya da sonraya bırakılan. Yoksa bu satırı yazma.
```

Kayda değer olmayan kısa oturumlar için betik tek satır ekler: `- 16:05 · 3 dk · codex · kısa oturum`.

## İşlemler

### Oturum işleme (otomatik)

Arka plan işçisi biten her oturum için bir özet (digest) verir. İşçi rolündeki ajan:

1. Oturum dosyasının sonuna yukarıdaki biçimde bölüm ekler.
2. Proje sayfasının `Durum` ve `Açık işler` bölümlerini günceller; karar varsa `Kararlar`'a ekler.
3. Kalıcı ve gerekçeli bir mimari karar varsa ADR açar (numara: mevcut en büyük + 1).
4. Başka projelerde de işe yarayacak bir öğrenim varsa Topic'i, yeni bir araç ya da servis varsa Entity'yi günceller ya da açar.
5. Kayda değer bir şey yoksa hiçbir dosyaya dokunmaz.
6. İşlenen oturum, proje sayfasına zaten işlenmiş daha yeni oturumlardan eskiyse (geçmiş işleme, başka makineden geç gelen paket) `Durum` ve `Açık işler` bölümlerine dokunmaz; yalnızca eksik kalıcı karar ve bilgiyi ekler.

### Elle kayıt

Kullanıcı "obsidiene geçir", "bunu not al" dediğinde `vault-hafiza` skill'i çalışır. Belirli bir içerik söylendiyse doğrudan doğru yere yazılır; yeri belli değilse `00-Inbox/YYYY-MM-DD <konu>.md`.

### Kaynak işleme (ingest)

`00-Inbox/`, `05-Raw/clippings/` ya da `05-Raw/files/` altındaki yeni bir dosya için (`vm ingest` çalıştırıldığında; işlenen dosyalar `99-Meta/System/ingested.txt` içinde tutulur):

1. Kaynağı oku. Ham dosyayı değiştirme, taşıma.
2. `04-Resources/Sources/` altına özet sayfası yaz; `raw` alanına ham dosyanın yolunu koy.
3. Kaynağın değdiği Topic, Entity ve proje sayfalarını güncelle; çelişkileri işaretle.

### Soru cevaplama (query)

1. Önce `index.md`'yi oku, ilgili sayfaları bul, sonra onları oku.
2. "Ne kadar çalıştım" türü sorular için `vm report` çıktısını kullan; süreyi kafadan hesaplama.
3. Cevabı sayfa linkleriyle ver. Cevap kalıcı değer taşıyorsa `04-Resources/Syntheses/` altına sayfa olarak kaydetmeyi öner.

### Sağlık kontrolü (lint)

`vm lint` kopuk linkleri, hiçbir yerden linklenmeyen sayfaları ve eksik frontmatter'ı raporlar. Anlam denetimi (çelişen ya da eskimiş iddialar, sayfası olmayan ama sık geçen kavramlar) ajan tarafından yapılır ve aynı rapora eklenir. Rapor `99-Meta/Lint/YYYY-MM-DD.md` dosyasına yazılır. Lint hiçbir sayfayı silmez.

## Yasaklar

- **Sır yazılmaz.** API anahtarı, token, şifre, özel anahtar, bağlantı dizesi vault'a asla girmez. Gerekirse "anahtar `.env` dosyasında, `X_API_KEY` adıyla" gibi yerini yaz, değerini yazma.
- `01-Journal/` içindeki metin değiştirilmez.
- `05-Raw/` altındaki dosyalar ve geçmiş oturum bölümleri değiştirilmez.
- Sayfa silinmez, dosya taşınmaz. Gereksiz görünen sayfa lint raporunda önerilir.
- `index.md` ve `log.md` elle düzenlenmez.
- İşçi rolündeki ajan git komutu çalıştırmaz; commit ve push'u betik yapar.

## Otomasyon

Betikler `99-Meta/System/` altındadır ve her makinede `~/.vault-memory/bin/vm` olarak erişilir.

| Komut | İş |
|---|---|
| `vm worker` | Bekleyen oturumları işler, commit ve push yapar |
| `vm worker --now` | Bekleme süresini beklemeden hemen işler |
| `vm report --project <ad> --from <tarih> --to <tarih>` | Proje ve gün bazında süre dökümü; `--json` makine okunur çıktı verir |
| `vm dashboard` | Süre panosunu `http://127.0.0.1:4747` adresinde açar |
| `vm ingest` | `00-Inbox/`, `05-Raw/clippings/` ve `05-Raw/files/` altındaki yeni dosyaları işler |
| `vm backfill --days 7 --project <ad>` | Kurulumdan önceki oturumları geçmiş kuyruğuna alır; yalnızca son N günün oturuşları işlenir, işçi bunları eskiden yeniye sırayla işler |
| `vm index` | `index.md`'yi yeniden üretir |
| `vm lint` | Sağlık raporu yazar |
| `vm sync` | pull, commit, push |
| `vm status` | Kuyruk ve son çalışma durumu; `--json` makine okunur çıktı verir |
| `vm capture` | İşlenmemiş oturumların ham özetini `outbox/<makine>` dalına gönderir (LLM çağırmaz) |
| `vm tick` | Zamanlayıcının çağırdığı giriş: önce `capture`, sonra `worker` |
| `vm config <anahtar> <değer>` | Bu makinenin ayarını gösterir ya da değiştirir |
| `vm install` / `vm uninstall` | Bu makineye hook, skill ve zamanlayıcıyı kurar ya da kaldırır |

### Makineler arası düzen

- Her makine kendi oturumlarını işler ve `99-Meta/System/processed.txt` defterine "makine, oturum, işlenen son konum" satırı ekler. Defter git ile paylaşılır; bir makine, başkasının işlediği oturumu ikinci kez işlemez.
- `capture` açık olan makine (ör. kapağı sık kapanan dizüstü), her ajan cevabından sonra işlenmemiş oturumlarının sırları temizlenmiş özetini `outbox/<makine>` dalına gönderir. Bu dal her seferinde üzerine yazılır, `main` geçmişine girmez.
- `process_remote` açık olan makine (ör. hep açık bir sunucu), bir paketin sahibi `remote_idle_minutes` (30 dk) içinde işlemediyse paketi kendisi işler ve kaydı paketin sahibinin adına yazar. Böylece kapağı kapatılan dizüstünün son oturumu da vault'a girer.
- Oturum dosyasındaki `minutes` ve `sessions` alanları dosyadaki `(N dk · araç)` başlıklarından yeniden hesaplanır; başlıktaki süreyi değiştirme.
