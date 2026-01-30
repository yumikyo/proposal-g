import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
from thefuzz import process, fuzz
from PIL import Image
import io

# --- ページ設定 ---
st.set_page_config(page_title="飲食店提案支援(アクト版)", layout="wide")

# --- 自社データの読み込み (エラー対策強化版) ---
@st.cache_data
def load_master_data():
    # ファイル名はシンプルに 'products.csv' に固定
    file_name = "products.csv"
    try:
        # 文字化け対策（utf-8-sig と shift-jis の両方を試す）
        try:
            df = pd.read_csv(file_name, encoding="utf-8-sig")
        except:
            df = pd.read_csv(file_name, encoding="shift-jis")
        
        # ご提示の項目名（アクト単価）を数値化
        if "アクト単価" in df.columns:
            df["アクト単価"] = pd.to_numeric(df["アクト単価"], errors='coerce').fillna(0)
        return df
    except FileNotFoundError:
        st.error(f"【重要】GitHubに '{file_name}' という名前のファイルが見つかりません。ファイル名を確認してください。")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"データの読み込み中にエラーが発生しました: {e}")
        return pd.DataFrame()

# --- 曖昧マッチング関数 ---
def find_best_match(ingredient_name, master_df, threshold=60):
    if master_df.empty or "商品名" not in master_df.columns:
        return None, 0
    
    choices = master_df["商品名"].astype(str).tolist()
    best_match_name, score = process.extractOne(ingredient_name, choices, scorer=fuzz.partial_token_sort_ratio)
    
    if score >= threshold:
        match_row = master_df[master_df["商品名"] == best_match_name].iloc[0]
        return match_row, score
    return None, 0

# --- メイン画面 ---
st.title("🍴 飲食店提案資料作成ツール (Gemini API)")
st.write("メニュー写真から食材を推測し、アクト商品との比較表を作成します。")

# サイドバー設定
with st.sidebar:
    st.header("⚙️ 設定 (Settings)")
    if "GOOGLE_API_KEY" in st.secrets:
        google_api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ APIキーは設定済みです")
    else:
        google_api_key = st.text_input("Google Gemini API Key", type="password")
        st.warning("StreamlitのSecretsにキーを設定すると、この入力は不要になります。")
    
    match_level = st.slider("マッチング精度", 0, 100, 60)

# 画像アップロード
uploaded_file = st.file_uploader("メニュー写真をアップロード", type=["jpg", "jpeg", "png"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象メニュー", width=400)

    if st.button("解析と提案資料作成を実行"):
        if not google_api_key:
            st.error("GoogleのAPIキーが設定されていません。")
        else:
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')

            with st.spinner('AIがメニューを分析し、アクト商品と照合中...'):
                try:
                    # プロンプトの実行
                    prompt = """
                    このメニュー写真から、使われている主要な食材を推測してください。
                    出力は必ず以下のJSON形式のみで答えてください。
                    {"materials": [{"name": "材料名", "market_price": 500, "qty": 1, "unit": "kg"}]}
                    """
                    response = model.generate_content([prompt, img])
                    
                    # AIの回答からJSONを抽出
                    raw_text = response.text.strip()
                    if "```json" in raw_text:
                        raw_text = raw_text.split("```json")[1].split("```")[0]
                    elif "```" in raw_text:
                        raw_text = raw_text.split("```")[1].split("```")[0]
                    
                    analysis_res = json.loads(raw_text)
                    master_df = load_master_data()
                    
                    proposal_list = []
                    for item in analysis_res.get("materials", []):
                        match, score = find_best_match(item["name"], master_df, match_level)
                        
                        row = {
                            "考えられる使用材料名\n(Estimated Ingredient)": item["name"],
                            "推定市場単価\n(Market Unit Price)": item["market_price"],
                            "自社商品No.\n(Product No)": match["アクト商品CD"] if match is not None else "---",
                            "自社商品名\n(Our Product Name)": match["商品名"] if match is not None else "該当なし/要確認",
                            "自社単価\n(Our Price)": match["アクト単価"] if match is not None else 0,
                            "数量\n(Qty)": item["qty"],
                            "単位\n(Unit)": match["［単位］"] if match is not None else item["unit"]
                        }
                        proposal_list.append(row)

                    if not proposal_list:
                        st.warning("食材がうまく抽出できませんでした。別の写真を試してください。")
                    else:
                        df_final = pd.DataFrame(proposal_list)
                        st.success("解析完了！")
                        
                        # テーブル表示（英語併記）
                        edited_df = st.data_editor(df_final, use_container_width=True, num_rows="dynamic")

                        # 削減額の計算
                        m_price = edited_df["推定市場単価\n(Market Unit Price)"].astype(float)
                        o_price = edited_df["自社単価\n(Our Price)"].astype(float)
                        qty = edited_df["数量\n(Qty)"].astype(float)
                        
                        total_market = (m_price * qty).sum()
                        total_our = (o_price * qty).sum()
                        
                        col1, col2 = st.columns(2)
                        col1.metric("推定市場コスト総額", f"¥{total_market:,.0f}")
                        col2.metric("自社切り替え時の削減額", f"¥{total_market - total_our:,.0f}", delta=float(total_our - total_market))

                        csv = edited_df.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("提案用CSV(日本語・英語併記)を保存", csv, "act_proposal.csv", "text/csv")

                except Exception as e:
                    st.error(f"解析中にエラーが発生しました: {e}")
