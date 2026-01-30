import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
from thefuzz import process, fuzz
from PIL import Image
import io

# --- ページ設定 ---
st.set_page_config(page_title="飲食店提案支援(Gemini版)", layout="wide")

# --- 自社データの読み込み ---
@st.cache_data
def load_master_data():
    try:
        # 日本語文字化け防止のためutf-8-sigで読み込み
        return pd.read_csv("products.csv", encoding="utf-8-sig")
    except:
        # ファイルがない場合の予備データ
        data = {
            "product_no": ["A-101", "T-505", "O-201"],
            "product_name": ["業務用パスタ 5kg", "ホールトマト缶", "EXVオリーブオイル"],
            "unit_price": [2000, 800, 7500],
            "unit": ["袋", "缶", "本"]
        }
        return pd.DataFrame(data)

# --- 曖昧マッチング関数 ---
def find_best_match(ingredient_name, master_df, threshold=60):
    choices = master_df["product_name"].tolist()
    best_match_name, score = process.extractOne(ingredient_name, choices, scorer=fuzz.partial_token_sort_ratio)
    
    if score >= threshold:
        match_row = master_df[master_df["product_name"] == best_match_name].iloc[0]
        return match_row, score
    return None, 0

# --- メイン画面 ---
st.title("🍴 飲食店提案資料作成ツール (Gemini API)")
st.write("メニュー写真から食材を推測し、自社商品との比較表を自動生成します。")

with st.sidebar:
    st.header("⚙️ 設定 (Settings)")
    # SecretsからAPIキーを取得
    if "GOOGLE_API_KEY" in st.secrets:
        google_api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("APIキーは設定済みです")
    else:
        google_api_key = st.text_input("Google Gemini API Key", type="password")
    
    match_level = st.slider("マッチング精度 (Match Sensitivity)", 0, 100, 60)

uploaded_file = st.file_uploader("メニュー写真をアップロード (Upload Menu Photo)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象メニュー", width=400)

    if st.button("解析と提案資料作成を実行"):
        if not google_api_key:
            st.error("APIキーを入力、またはSecretsに設定してください。")
        else:
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')

            with st.spinner('AIが食材を分析し、自社商品と照合しています...'):
                try:
                    prompt = """
                    この飲食店メニュー写真から、使われている主要な食材を推測してください。
                    出力は必ず以下のJSON形式のみで答えてください。
                    {"materials": [{"name": "材料名", "market_price": 500, "qty": 1, "unit": "kg"}]}
                    """
                    
                    response = model.generate_content([prompt, img])
                    clean_json = response.text.replace('```json', '').replace('```', '').strip()
                    analysis_res = json.loads(clean_json)
                    
                    master_df = load_master_data()
                    proposal_list = []
                    
                    for item in analysis_res["materials"]:
                        match, score = find_best_match(item["name"], master_df, match_level)
                        
                        row = {
                            "考えられる使用材料名\n(Estimated Ingredient)": item["name"],
                            "推定市場単価\n(Market Unit Price)": item["market_price"],
                            "自社商品No.\n(Product No)": match["product_no"] if match is not None else "---",
                            "自社商品名\n(Our Product Name)": match["product_name"] if match is not None else "該当なし",
                            "自社単価\n(Our Price)": match["unit_price"] if match is not None else 0,
                            "数量\n(Qty)": item["qty"],
                            "単位\n(Unit)": match["unit"] if match is not None else item["unit"]
                        }
                        proposal_list.append(row)

                    df_final = pd.DataFrame(proposal_list)
                    st.success("解析が完了しました。")
                    
                    # 編集可能なテーブル
                    edited_df = st.data_editor(df_final, use_container_width=True, num_rows="dynamic")

                    # 削減額の計算
                    total_market = (edited_df["推定市場単価\n(Market Unit Price)"] * edited_df["数量\n(Qty)"]).sum()
                    total_our = (edited_df["自社単価\n(Our Price)"] * edited_df["数量\n(Qty)"]).sum()
                    
                    c1, c2 = st.columns(2)
                    c1.metric("推定市場コスト総額", f"¥{total_market:,.0f}")
                    c2.metric("自社切り替え時の削減額", f"¥{total_market - total_our:,.0f}")

                    # ダウンロード用CSV（日本語文字化け防止のためutf-8-sig）
                    csv = edited_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("提案資料(CSV)をダウンロード", csv, "proposal.csv", "text/csv")

                except Exception as e:
                    st.error(f"エラー: {str(e)}")
