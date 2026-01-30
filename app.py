import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import os
import re
import base64
import io
from PIL import Image
from thefuzz import process, fuzz

# ----------------------------
# 1. 初期設定 & Runwithデザイン
# ----------------------------
st.set_page_config(page_title="Runwith Cost Analyzer", layout="wide", page_icon="📊")

# Runwith専用ハイコントラストデザイン
st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Helvetica Neue', sans-serif; }
    .stButton>button { 
        font-weight: bold; font-size: 18px; min-height: 60px; border-radius: 10px;
        background-color: #FF851B; color: #001F3F; border: 2px solid #001F3F;
    }
    .stButton>button:hover { background-color: #e67616; color: #FFFFFF; }
    label { font-size: 18px !important; font-weight: bold !important; color: #FF851B !important; }
    .main-header {
        background: linear-gradient(135deg, #001F3F 0%, #003366 100%);
        color: #FFFFFF; padding: 30px; border-radius: 20px; text-align: center;
        margin-bottom: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# 2. 関数定義（データ処理・AI）
# ----------------------------

@st.cache_data
def load_products():
    """アクト商品データの読み込み"""
    # ファイル名はシンプルに 'products.csv' を想定
    file_path = "products.csv"
    try:
        if not os.path.exists(file_path):
            st.error(f"⚠️ '{file_path}' が見つかりません。GitHubにアップロードされているか確認してください。")
            return pd.DataFrame()
        
        # 文字コード対応
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
        except:
            df = pd.read_csv(file_path, encoding="shift-jis")
            
        # アクト単価を数値化
        if "アクト単価" in df.columns:
            df["アクト単価"] = pd.to_numeric(df["アクト単価"], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame()

def find_best_match(ingredient_name, master_df, threshold):
    """曖昧マッチングによる自社商品特定"""
    if master_df.empty or "商品名" not in master_df.columns:
        return None, 0
    
    choices = master_df["商品名"].astype(str).tolist()
    best_match_name, score = process.extractOne(ingredient_name, choices, scorer=fuzz.partial_token_sort_ratio)
    
    if score >= threshold:
        match_row = master_df[master_df["商品名"] == best_match_name].iloc[0]
        return match_row, score
    return None, 0

# ----------------------------
# 3. サイドバー（設定）
# ----------------------------
with st.sidebar:
    st.markdown("<div style='background:#001F3F;color:#FF851B;padding:20px;border-radius:15px;text-align:center;font-weight:bold;font-size:18px;'>Runwith Cost Analyzer</div>", unsafe_allow_html=True)
    
    st.header("🔧 システム設定")
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ APIキー認証済み")
    else:
        api_key = st.text_input("🔑 Gemini APIキー", type="password")
    
    st.divider()
    st.header("🎯 照合設定")
    match_level = st.slider("マッチングの厳格度", 0, 100, 60, help="高いほど正確な一致を求めます")
    
    st.divider()
    st.caption("© 2026 Runwith AI Consulting")

# ----------------------------
# 4. メインコンテンツ
# ----------------------------
st.markdown("""
<div class='main-header'>
    <h1>📊 Runwith 商品比較提案ツール</h1>
    <p style='font-size: 1.2em; color: #FF851B; font-weight: bold;'>
        メニュー写真から使用材料を推測し、コスト削減案を自動作成します
    </p>
</div>
""", unsafe_allow_html=True)

# ステップ1: お店情報
st.markdown("### 🏪 1. 提案先情報")
col1, col2 = st.columns(2)
with col1:
    client_name = st.text_input("🏠 店舗名", placeholder="例：新規開拓レストラン")
with col2:
    target_menu = st.text_input("📖 対象メニュー名", placeholder="例：看板パスタランチ")

st.divider()

# ステップ2: 写真の登録
st.markdown("### 📸 2. メニュー写真のアップロード")
uploaded_file = st.file_uploader("メニューを撮影した画像を選択してください", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象画像", width=400)

    # ステップ3: 解析実行
    st.markdown("---")
    if st.button("🚀 提案資料を生成する", type="primary", use_container_width=True):
        if not api_key:
            st.error("Gemini APIキーを設定してください。")
        elif not client_name:
            st.warning("店舗名を入力してください。")
        else:
            with st.spinner('Runwith AI が材料を分析し、アクト商品と照合中...'):
                try:
                    # AI設定
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')

                    # AIへの指示
                    prompt = """
                    役割: 卸売業者の優秀な営業コンサルタント。
                    指示: 画像のメニューから使われている主な材料を推測してください。
                    出力フォーマット: 必ず以下のJSON形式のみで答えてください。
                    {"materials": [{"name": "材料名", "market_price": 500, "qty": 1, "unit": "kg"}]}
                    ※market_priceは一般的な市場単価（円）を想定してください。
                    """
                    
                    response = model.generate_content([prompt, img])
                    
                    # JSONの抽出
                    json_match = re.search(r'\[.*\]|\{.*\}', response.text, re.DOTALL)
                    if not json_match:
                        raise Exception("AIの解析結果が正しく取得できませんでした。")
                    
                    analysis_res = json.loads(json_match.group())
                    master_df = load_products()
                    
                    # 照合ロジック
                    proposal_data = []
                    materials_list = analysis_res.get("materials", [])
                    
                    for item in materials_list:
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

                    # 結果の表示
                    if proposal_data:
                        st.session_state.proposal_result = pd.DataFrame(proposal_data)
                        st.success("✨ 提案資料のベースが完成しました！")
                    else:
                        st.warning("材料を特定できませんでした。別の写真を試してください。")

                except Exception as e:
                    st.error(f"解析エラー: {e}")

# 結果の表示と編集
if 'proposal_result' in st.session_state:
    st.markdown("### 📊 3. 提案比較表")
    st.info("💡 表の中身は直接編集できます。実際の商談に合わせて調整してください。")
    
    # データエディタ
    edited_df = st.data_editor(st.session_state.proposal_result, use_container_width=True, num_rows="dynamic")
    
    # 計算処理
    m_total = (edited_df["推定市場単価\n(Market Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    o_total = (edited_df["自社単価\n(Our Price)"].astype(float) * edited_df["数量\n(Qty)"].astype(float)).sum()
    diff = m_total - o_total
    
    # コスト削減額の表示（Runwithカラー）
    c1, c2, c3 = st.columns(3)
    c1.metric("推定市場コスト総額", f"¥{m_total:,.0f}")
    c2.metric("アクト切り替え後の総額", f"¥{o_total:,.0f}")
    c3.metric("コスト削減見込", f"¥{diff:,.0f}", delta=float(diff))

    # ダウンロード
    st.divider()
    csv = edited_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 提案用CSVデータをダウンロード",
        data=csv,
        file_name=f"Runwith_Proposal_{client_name}.csv",
        mime="text/csv",
        use_container_width=True
    )

st.markdown("---")
st.caption("Developed by Runwith AI System - Supporting Your Sales Excellence.")
