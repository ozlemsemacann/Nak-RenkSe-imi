import streamlit as st
import numpy as np
import json
import os
from PIL import Image, ImageEnhance
from skimage import color
import easyocr
from streamlit_image_coordinates import streamlit_image_coordinates

# --- YOLLAR ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KARTELA_KLASORU = os.path.join(BASE_DIR, "kartelalar")
HAFIZA_DOSYASI = os.path.join(BASE_DIR, "tuana_hafiza.json")

st.set_page_config(page_title="Tuana Sayfa No Destekli Analiz", layout="wide")

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

reader = load_ocr()

def sayfa_no_ile_tara_ve_kaydet():
    database = []
    if not os.path.exists(KARTELA_KLASORU):
        st.error("HATA: 'kartelalar' klasoru bulunamad?!")
        return []

    resimler = [f for f in os.listdir(KARTELA_KLASORU) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    st.info(f"?? {len(resimler)} sayfa taran?yor...")
    progress_bar = st.progress(0)
    
    for i, dosya_adi in enumerate(resimler):
        yol = os.path.join(KARTELA_KLASORU, dosya_adi)
        try:
            img_rgb = np.array(Image.open(yol).convert('RGB'))
        except: continue
        
        results = reader.readtext(img_rgb)
        h, w, _ = img_rgb.shape

        # --- SAYFA NUMARASINI BUL (Gorselin en solundaki daire icindeki say?) ---
        # Genellikle koordinat olarak x < 150 ve y < 200 bolgesindedir
        sayfa_no = "X"
        for (bbox, text, prob) in results:
            clean = "".join(filter(str.isdigit, text))
            (tl, tr, br, bl) = bbox
            # Sayfa no genelde sol ba?ta (x < 150) ve 1-2 hanelidir
            if 1 <= len(clean) <= 2 and tl[0] < 150:
                sayfa_no = clean
                break

        for (bbox, text, prob) in results:
            clean_code = "".join(filter(str.isdigit, text))
            # Sadece 3-4 haneli iplik kodlar?n? al
            if 3 <= len(clean_code) <= 4 and prob > 0.80:
                (tl, tr, br, bl) = bbox
                cx = int((tl[0] + tr[0]) / 2)
                
                # Rengi ipli?in oldu?u alt k?s?mdan al (Siyah band? atla)
                best_color = None
                max_sat = -1
                search_start = int(br[1]) + 90 
                search_end = min(h, search_start + 70)
                
                for y_off in range(search_start, search_end, 5):
                    c = img_rgb[y_off, cx]
                    sat = int(np.max(c)) - int(np.min(c))
                    if sat > max_sat and np.mean(c) > 30: 
                        max_sat = sat
                        best_color = c.tolist()
                
                if best_color:
                    # Kay?t format?: "SAYFA NO - ?PL?K KODU"
                    database.append({"kod": f"{sayfa_no} - {clean_code}", "rgb": best_color})
        
        progress_bar.progress((i + 1) / len(resimler))
    
    with open(HAFIZA_DOSYASI, "w") as f:
        json.dump(database, f)
    return database

def en_yakin_bul(target_rgb, db, p_adj):
    img_t = Image.new('RGB', (1,1), tuple(target_rgb))
    target_rgb_adj = np.array(ImageEnhance.Brightness(img_t).enhance(p_adj).getpixel((0,0)))
    target_lab = color.rgb2lab(target_rgb_adj.reshape(1,1,3)/255.0)[0][0]
    
    res = []
    for item in db:
        c_lab = color.rgb2lab(np.array(item['rgb']).reshape(1,1,3)/255.0)[0][0]
        de = color.deltaE_ciede2000(target_lab, c_lab)
        score = max(0, 100 - (de * 2.5))
        res.append({"kod": item['kod'], "rgb": item['rgb'], "de": de, "score": score})
    return sorted(res, key=lambda x: x['de'])[:3]

# --- ARAYUZ ---
if not os.path.exists(HAFIZA_DOSYASI):
    st.button("🚀 SAYFA NO DESTEKLİ TARAMAYI BAŞLAT", on_click=sayfa_no_ile_tara_ve_kaydet)
else:
    with open(HAFIZA_DOSYASI, "r") as f:
        db = json.load(f)

    st.sidebar.button("🗑️ Hafızayı Sıfırla (Yeniden Tara)", on_click=lambda: os.remove(HAFIZA_DOSYASI) if os.path.exists(HAFIZA_DOSYASI) else None)
    p_val = st.sidebar.slider("Işık Ayarı", 0.5, 1.5, 1.0)

    up = st.file_uploader("Analiz edilecek resmi yükle", type=["jpg", "png", "jpeg"])
    if up:
        img_up = Image.open(up)
        coords = streamlit_image_coordinates(img_up, key="p")
        if coords:
            rgb = np.array(img_up)[coords["y"], coords["x"]]
            results = en_yakin_bul(rgb, db, p_val)
            cols = st.columns(3)
            for i, r in enumerate(results):
                with cols[i]:
                    st.write(f"### %{r['score']:.1f} Uyum")
                    st.metric(f"Sayfa - Kod: {r['kod']}", f"Delta-E: {r['de']:.1f}")

                    st.markdown(f'<div style="background:rgb{tuple(r["rgb"])};height:60px;border-radius:10px;border:2px solid #000"></div>', unsafe_allow_html=True)
