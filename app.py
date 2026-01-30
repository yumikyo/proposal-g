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
# 1. デザイン設定（ハイコントラスト・ネイビー＆オレンジ）
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
# 2. ロジック（データ読み込み・マッチング）
# ----------------------------

@st.cache_data
def load_products():
    file_path = "products.csv"
    try:
        if not os.path.exists(file_path):
            st.error(f"ファイル '{file_path}' が見つかりません。")
            return pd.DataFrame()
        
        # 文字コード対応（UTF-8 または Shift-JIS）
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
        except:
            df = pd.read_csv(file_path, encoding="shift-jis")
            
        # 単価データの数値化
        if "アクト単価" in df.columns:
            df["アクト単価"] = pd.to_numeric(df["アクト単価"], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame()

def find_best_match(ingredient_name, master_df, threshold):
    if master_df.empty or "商品 name" not in master_df.columns and "商品名" not in master_df.columns:
        return None, 0
    
    # 列名が「商品名」であることを前提とする
    col_name = "商品名" if "商品名" in master_df.columns else master_df.columns[1]
    choices = master_df[col_name].astype(str).tolist()
    best_match_name, score = process.extractOne(ingredient_name, choices, scorer=fuzz.partial_token_sort_ratio)
    
    if score >= threshold:
        match_row = master_df[master_df[col_name] == best_match_name].iloc[0]
        return match_row, score
    return None, 0

# ----------------------------
# 3. サイドバー
# ----------------------------
with st.sidebar:
    st.markdown("<div style='background:#001F3F;color:#FF851B;padding:15px;border-radius:10px;text-align:center;font-weight:bold;font-size:1.2em;'>提案ツール設定</div>", unsafe_allow_html=True)
    
    st.header("🔑 認証")
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ 認証済み")
    else:
        api_key = st.text_input("Gemini APIキーを入力", type="password")
    
    st.divider()
    match_level = st.slider("マッチング感度", 0, 100, 60)
    st.caption("食品卸売提案支援システム v2.1")

# ----------------------------
# 4. メイン画面
# ----------------------------
st.markdown("""
<div class='main-header'>
    <h1>🍴 新規開拓・食材比較提案システム</h1>
    <p style='font-size: 1.1em; color: #FF851B; font-weight: bold;'>
        メニュー解析からコスト削減シミュレーションを自動生成
    </p>
</div>
""", unsafe_allow_html=True)

# 情報入力セクション
st.markdown("### 📋 1. 提案・担当者情報")
c1, c2, c3 = st.columns(3)
with c1:
    cust_name = st.text_input("お客様名（店舗名）", placeholder="〇〇レストラン 御中")
with c2:
    cust_contact = st.text_input("連絡先（電話/担当名）", placeholder="090-xxxx-xxxx / 担当：〇〇様")
with c3:
    staff_name = st.text_input("自社担当者名", placeholder="営業部：〇〇")

st.divider()

# 画像セクション
st.markdown("### 📸 2. メニュー写真の解析")
uploaded_file = st.file_uploader("撮影したメニュー写真をアップロード", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象", width=400)

    if st.button("🔍 メニューを解析して提案を作成", type="primary", use_container_width=True):
        if not api_key:
            st.error("APIキーを設定してください。")
        elif not cust_name:
            st.warning("お客様名を入力してください。")
        else:
            with st.spinner('AIが材料を推測し、自社マスタと照合中...'):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')

                    prompt = """
                    メニュー写真から使われている主な材料を推測してください。
                    必ず以下のJSON形式のみで回答してください。
                    {"materials": [{"name": "材料名", "market_price": 500, "qty": 1, "unit": "kg"}]}
                    ※market_priceは競合他社の一般的な市場卸単価（円）の推測値です。
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
                        st.session_state.p_result = pd.DataFrame(proposal_data)
                        st.success("✅ 比較表が完成しました")
                    else:
                        st.warning("材料を特定できませんでした。")

                except Exception as e:
                    st.error(f"解析エラー: {e}")

# 結果表示セクション
if 'p_result' in st.session_state:
    st.markdown("### 📊 3. コスト比較提案表")
    st.info(f"宛先：{cust_name} 様　／　連絡先：{cust_contact}　／　担当者：{staff_name}")
    
    # 編集可能な表
    edited_df = st.data_editor(st.session_state.p_result, use_container_width=True, num_rows="dynamic")
    
    # 合計額の算出
    m_sum = (edited_df["推定市場単価\n(Market Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    o_sum = (edited_df["自社単価\n(Our Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    diff = m_sum - o_sum
    
    # 削減効果の表示
    col1, col2, col3 = st.columns(3)
    col1.metric("推定市場総額", f"¥{m_sum:,.0f}")
    col2.metric("自社切り替え総額", f"¥{o_sum:,.0f}")
    col3.metric("月間削減見込額", f"¥{diff:,.0f}", delta=float(diff))

    st.divider()
    
    # CSVダウンロード（ヘッダーに情報を付与）
    csv_body = edited_df.to_csv(index=False)
    header_info = f"お客様名,{cust_name}\n連絡先,{cust_contact}\n自社担当者,{staff_name}\n\n"
    full_csv = (header_info + csv_body).encode('utf-8-sig')
    
    st.download_button(
        label="📥 提案用CSVファイルをダウンロード",
        data=full_csv,
        file_name=f"提案書_{cust_name}.csv",
        mime="text/csv",
        use_container_width=True
    )

st.markdown("---")
st.caption("食品卸売支援システム - 現場の営業活動をAIで加速させます。")
