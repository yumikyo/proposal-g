import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import os
import re
import io
from PIL import Image
from thefuzz import process, fuzz

# ----------------------------
# 1. ページ設定とデザイン
# ----------------------------
st.set_page_config(page_title="食材比較提案システム", layout="wide")

st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Hiragino Kaku Gothic ProN', 'Meiryo', sans-serif; }
    .stButton>button { 
        font-weight: bold; font-size: 20px; min-height: 65px; border-radius: 12px;
        background-color: #FF851B; color: #001F3F; border: 2px solid #001F3F;
    }
    label { font-size: 18px !important; font-weight: bold !important; color: #FF851B !important; }
    .main-header {
        background: linear-gradient(135deg, #001F3F 0%, #003366 100%);
        color: #FFFFFF; padding: 35px; border-radius: 15px; text-align: center;
        margin-bottom: 30px; border-bottom: 5px solid #FF851B;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# 2. ロジック（APIキー取得・データ読み込み）
# ----------------------------

def get_api_key():
    """Secretsから複数の候補名でAPIキーを探す"""
    # 候補1: GEMINI_API_KEY
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    # 候補2: GOOGLE_API_KEY
    if "GOOGLE_API_KEY" in st.secrets:
        return st.secrets["GOOGLE_API_KEY"]
    return None

@st.cache_data
def load_products():
    """アクト商品データの読み込み"""
    # GitHub上のファイル名を 'products.csv' にしている前提
    file_path = "products.csv"
    try:
        if not os.path.exists(file_path):
            st.error(f"ファイル '{file_path}' が見つかりません。")
            return pd.DataFrame()
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
        except:
            df = pd.read_csv(file_path, encoding="shift-jis")
        if "アクト単価" in df.columns:
            df["アクト単価"] = pd.to_numeric(df["アクト単価"], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame()

def find_best_match(ingredient_name, master_df, threshold):
    """商品名との曖昧マッチング"""
    if master_df.empty or "商品名" not in master_df.columns:
        return None, 0
    choices = master_df["商品名"].astype(str).tolist()
    best_match_name, score = process.extractOne(ingredient_name, choices, scorer=fuzz.partial_token_sort_ratio)
    if score >= threshold:
        match_row = master_df[master_df["商品名"] == best_match_name].iloc[0]
        return match_row, score
    return None, 0

# ----------------------------
# 3. メイン画面
# ----------------------------
st.markdown("""
<div class='main-header'>
    <h1>🍴 新規開拓・食材比較提案システム</h1>
    <p style='font-size: 1.1em; color: #FF851B; font-weight: bold;'>
        メニュー解析からコスト削減シミュレーションを自動生成
    </p>
</div>
""", unsafe_allow_html=True)

# キーの取得と警告表示
api_key = get_api_key()

with st.sidebar:
    st.markdown("<div style='background:#001F3F;color:#FF851B;padding:15px;border-radius:10px;text-align:center;font-weight:bold;'>設定</div>", unsafe_allow_html=True)
    if api_key:
        st.success("✅ Secretsからキーを読み込みました")
    else:
        st.warning("⚠️ Secretsにキーが見つかりません。以下に入力するかSecretsを設定してください。")
        api_key = st.text_input("Gemini APIキーを直接入力", type="password")
    
    match_level = st.slider("マッチング感度", 0, 100, 60)
    st.caption("食品卸売提案支援システム v2.2")

# 1. 顧客情報入力
st.markdown("### 📋 1. 提案・担当者情報")
c1, c2, c3 = st.columns(3)
with c1:
    cust_name = st.text_input("お客様名（店舗名）", placeholder="〇〇レストラン 御中")
with c2:
    cust_contact = st.text_input("連絡先（電話/担当名）", placeholder="090-xxxx-xxxx / 担当：〇〇様")
with c3:
    staff_name = st.text_input("自社担当者名", placeholder="営業部：〇〇")

st.divider()

# 2. 画像解析
st.markdown("### 📸 2. メニュー写真の解析")
uploaded_file = st.file_uploader("メニュー写真をアップロード", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象", width=400)

    if st.button("🔍 解析を実行して比較表を作成", type="primary", use_container_width=True):
        if not api_key:
            st.error("APIキーが必要です。Secretsに GEMINI_API_KEY を設定してください。")
        elif not cust_name:
            st.warning("お客様名を入力してください。")
        else:
            with st.spinner('解析中...'):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt = """
                    メニュー写真から使われている主な材料を推測してください。
                    必ず以下のJSON形式のみで回答してください。
                    {"materials": [{"name": "材料名", "market_price": 500, "qty": 1, "unit": "kg"}]}
                    """
                    response = model.generate_content([prompt, img])
                    json_str = re.search(r'\[.*\]|\{.*\}', response.text, re.DOTALL).group()
                    analysis_res = json.loads(json_str)
                    
                    master_df = load_products()
                    proposal_data = []
                    
                    for item in analysis_res.get("materials", []):
                        match, score = find_best_match(item["name"], master_df, match_level)
                        proposal_data.append({
                            "考えられる使用材料名\n(Estimated Ingredient)": item["name"],
                            "推定市場単価\n(Market Price)": item["market_price"],
                            "自社商品No.\n(Product No)": match["アクト商品CD"] if match is not None else "---",
                            "自社商品名\n(Our Product Name)": match["商品名"] if match is not None else "該当なし/要確認",
                            "自社単価\n(Our Price)": match["アクト単価"] if match is not None else 0,
                            "数量\n(Qty)": item["qty"],
                            "単位\n(Unit)": match["［単位］"] if match is not None else item["unit"]
                        })

                    if proposal_data:
                        st.session_state.p_data = pd.DataFrame(proposal_data)
                    else:
                        st.error("解析結果が空でした。別の写真を試してください。")
                except Exception as e:
                    st.error(f"解析エラー: {e}")

# 3. 結果表示
if 'p_data' in st.session_state:
    st.markdown("### 📊 3. コスト比較提案表")
    edited_df = st.data_editor(st.session_state.p_data, use_container_width=True, num_rows="dynamic")
    
    m_sum = (edited_df["推定市場単価\n(Market Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    o_sum = (edited_df["自社単価\n(Our Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    diff = m_sum - o_sum
    
    col1, col2, col3 = st.columns(3)
    col1.metric("推定市場総額", f"¥{m_sum:,.0f}")
    col2.metric("自社切り替え総額", f"¥{o_sum:,.0f}")
    col3.metric("削減見込額", f"¥{diff:,.0f}", delta=float(diff))

    st.divider()
    csv_body = edited_df.to_csv(index=False)
    header_info = f"お客様名,{cust_name}\n連絡先,{cust_contact}\n自社担当者,{staff_name}\n\n"
    full_csv = (header_info + csv_body).encode('utf-8-sig')
    
    st.download_button("📥 提案用CSVを保存", data=full_csv, file_name=f"提案書_{cust_name}.csv", mime="text/csv", use_container_width=True)

st.markdown("---")
st.caption("食品卸売支援システム - 営業活動をAIで最適化します。")
