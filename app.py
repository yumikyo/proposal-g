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
# 1. デザイン設定（ネイビー＆オレンジ）
# ----------------------------
st.set_page_config(page_title="食材比較提案システム", layout="wide")

st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Hiragino Kaku Gothic ProN', 'Meiryo', sans-serif; }
    
    /* ボタンデザイン */
    .stButton>button { 
        font-weight: bold; font-size: 20px; min-height: 65px; border-radius: 12px;
        background-color: #FF851B; color: #001F3F; border: 2px solid #001F3F;
    }
    .stButton>button:hover { background-color: #e67616; color: #FFFFFF; }

    /* 入力項目ラベル */
    label { font-size: 18px !important; font-weight: bold !important; color: #FF851B !important; }

    /* ヘッダー */
    .main-header {
        background: linear-gradient(135deg, #001F3F 0%, #003366 100%);
        color: #FFFFFF; padding: 35px; border-radius: 15px; text-align: center;
        margin-bottom: 30px; border-bottom: 5px solid #FF851B;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# 2. ロジック設定
# ----------------------------

def get_api_key():
    """SecretsからAPIキーを取得"""
    for key_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
        if key_name in st.secrets:
            return st.secrets[key_name]
    return None

@st.cache_data
def load_products():
    """アクト商品データの読み込み"""
    file_path = "products.csv"
    try:
        if not os.path.exists(file_path):
            st.error(f"⚠️ ファイル '{file_path}' が見つかりません。")
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

api_key = get_api_key()

with st.sidebar:
    st.markdown("<div style='background:#001F3F;color:#FF851B;padding:15px;border-radius:10px;text-align:center;font-weight:bold;'>システム設定</div>", unsafe_allow_html=True)
    if api_key:
        st.success("✅ APIキーを読み込みました")
    else:
        st.warning("⚠️ Secretsにキーが見つかりません。")
        api_key = st.text_input("Gemini APIキーを直接入力", type="password")
    
    match_level = st.slider("マッチング感度", 0, 100, 60)

# 1. 提案・担当者情報（すべて任意入力）
st.markdown("### 📋 1. 提案・担当者情報（後日入力可）")
c1, c2, c3 = st.columns(3)
with c1:
    cust_name = st.text_input("お客様名（店舗名）", placeholder="例：〇〇レストラン 御中")
with c2:
    cust_contact = st.text_input("連絡先（電話番号/担当者）", placeholder="例：090-xxxx-xxxx")
with c3:
    staff_name = st.text_input("自社担当者名", placeholder="例：営業 〇〇")

st.divider()

# 2. メニュー解析
st.markdown("### 📸 2. メニュー写真の解析")
uploaded_file = st.file_uploader("メニューを撮影した写真をアップロード", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象画像", width=400)

    if st.button("🔍 解析を実行して比較表を作成", type="primary", use_container_width=True):
        if not api_key:
            st.error("APIキーが必要です。Secretsの設定を確認してください。")
        else:
            with st.spinner('AIが食材を分析中...'):
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
                    proposal_list = []
                    
                    for item in analysis_res.get("materials", []):
                        match, score = find_best_match(item["name"], master_df, match_level)
                        proposal_list.append({
                            "考えられる使用材料名\n(Estimated Ingredient)": item["name"],
                            "推定市場単価\n(Market Price)": item["market_price"],
                            "自社商品No.\n(Product No)": match["アクト商品CD"] if match is not None else "---",
                            "自社商品名\n(Our Product Name)": match["商品名"] if match is not None else "該当なし/要確認",
                            "自社単価\n(Our Price)": match["アクト単価"] if match is not None else 0,
                            "数量\n(Qty)": item["qty"],
                            "単位\n(Unit)": match["［単位］"] if match is not None else item["unit"]
                        })

                    if proposal_list:
                        st.session_state.result_df = pd.DataFrame(proposal_list)
                    else:
                        st.error("食材が抽出できませんでした。")
                except Exception as e:
                    st.error(f"解析エラー: {e}")

# 3. 比較表
if 'result_df' in st.session_state:
    st.markdown("### 📊 3. コスト比較提案表")
    edited_df = st.data_editor(st.session_state.result_df, use_container_width=True, num_rows="dynamic")
    
    m_sum = (edited_df["推定市場単価\n(Market Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    o_sum = (edited_df["自社単価\n(Our Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    diff = m_sum - o_sum
    
    col1, col2, col3 = st.columns(3)
    col1.metric("推定市場コスト総額", f"¥{m_sum:,.0f}")
    col2.metric("自社切り替え総額", f"¥{o_sum:,.0f}")
    col3.metric("月間削減見込額", f"¥{diff:,.0f}", delta=float(diff))

    st.divider()
    
    # CSV保存処理（未入力でも動作するように調整）
    csv_body = edited_df.to_csv(index=False)
    header = f"お客様名,{cust_name}\n連絡先,{cust_contact}\n自社担当者,{staff_name}\n\n"
    full_csv = (header + csv_body).encode('utf-8-sig')
    
    filename = f"提案書_{cust_name}.csv" if cust_name else "提案書.csv"
    
    st.download_button("📥 提案資料(CSV)を保存する", data=full_csv, file_name=filename, mime="text/csv", use_container_width=True)

st.markdown("---")
