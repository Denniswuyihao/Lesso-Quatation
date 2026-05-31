import streamlit as st
import pandas as pd
import numpy as np

# 1. 网页基础配置
st.set_page_config(page_title="联塑外贸智能PI报价与利润精算平台", layout="wide", initial_sidebar_state="expanded")

# --- 2. 核心函数：智能兼容管材表与阀门表的动态解析器 ---
def smart_parse_dictionary(df):
    """
    智能解析联塑两种不同排版的表格模板：
    Layout 1 (管材/管件): 产品名称, Size(mm), SAP No., 物料描述, Pcs/Carton, L, W, H, CBM
    Layout 2 (阀门类): 规格, 物料号, I型单价, 重量/kg, 物料号.1, II型单价...
    """
    cleaned_rows = []
    cols = df.columns.astype(str).str.strip().tolist()
    
    # 判断是否为阀门横向并排排版 (检查是否含有 'I型' 或 '物料号' 重复)
    is_valve_layout = any("型" in c for c in cols) or "物料号" in cols
    
    if is_valve_layout:
        # 针对阀门多变体排版进行“降维打击”横向转纵向清洗
        for idx, row in df.iterrows():
            prod_name = row.get("产品名称", "阀门产品")
            spec = row.get("规格", row.get("规格(mm)", ""))
            
            # 扫描这一行所有可能存在的物料号列
            for col_idx, col_name in enumerate(cols):
                if "物料号" in col_name and pd.notna(row.iloc[col_idx]):
                    sap_code = str(row.iloc[col_idx]).split('.')[0].strip()
                    if not sap_code or sap_code.lower() == 'nan' or sap_code == '/': 
                        continue
                        
                    # 动态抓取紧随其后的单价和重量
                    price = 0.0
                    weight = 0.0
                    if col_idx + 1 < len(cols): price = row.iloc[col_idx + 1]
                    if col_idx + 2 < len(cols): weight = row.iloc[col_idx + 2]
                    
                    cleaned_rows.append({
                        "SAP号": sap_code,
                        "产品名称": prod_name,
                        "尺寸规格": spec,
                        "物料描述": f"{prod_name} {spec}",
                        "Weight": weight if pd.notna(weight) and isinstance(weight, (int, float)) else 0.0,
                        "Pcs_Carton": 1, "L": 0.0, "W": 0.0, "H": 0.0, "CBM": 0.0
                    })
    else:
        # 针对标准的管材/管件模板
        # 动态兼容中英文表头名字
        sap_col = next((c for c in cols if "SAP" in c or "物料号" in c), "SAP号")
        name_col = next((c for c in cols if "名称" in c or "Name" in c), "产品名称")
        desc_col = next((c for c in cols if "描述" in c or "Desc" in c), "物料描述")
        size_col = next((c for c in cols if "Size" in c or "规格" in c), "尺寸规格")
        weight_col = next((c for c in cols if "Weight" in c or "重量" in c), "Weight")
        pcs_col = next((c for c in cols if "Pcs" in c or "装箱" in c or "Carton" in c), "Pcs/Carton")
        
        for idx, row in df.iterrows():
            sap_code = str(row.get(sap_col, "")).split('.')[0].strip()
            if not sap_code or sap_code.lower() == 'nan': 
                continue
            
            # 计算体积：判断长宽高是以米还是毫米为单位
            l_val = float(row.get("L", 0)) if pd.notna(row.get("L", 0)) else 0.0
            w_val = float(row.get("W", 0)) if pd.notna(row.get("W", 0)) else 0.0
            h_val = float(row.get("H", 0)) if pd.notna(row.get("H", 0)) else 0.0
            
            cbm_val = float(row.get("CBM", 0)) if pd.notna(row.get("CBM", 0)) else 0.0
            if cbm_val == 0 and (l_val * w_val * h_val) > 0:
                if l_val > 10:
                    cbm_val = (l_val * w_val * h_val) / 1e9
                else:
                    cbm_val = l_val * w_val * h_val
            
            cleaned_rows.append({
                "SAP号": sap_code,
                "产品名称": row.get(name_col, ""),
                "尺寸规格": row.get(size_col, ""),
                "物料描述": row.get(desc_col, row.get(name_col, "")),
                "Weight": row.get(weight_col, 0.0),
                "Pcs_Carton": row.get(pcs_col, 1),
                "L": l_val, "W": w_val, "H": h_val,
                "CBM": round(cbm_val, 6)
            })
            
    return pd.DataFrame(cleaned_rows) if cleaned_rows else None


# --- 3. 初始化全局状态与高还原度模拟数据 ---
if 'product_dictionary' not in st.session_state:
    # 默认初始化数据，包含真实经典SKU
    st.session_state.product_dictionary = pd.DataFrame({
        "SAP号": ["8010034798", "8010031990", "8010041365", "8060020258"],
        "产品名称": ["PE给水管，1.0MPa SDR17", "PE给水管，1.0MPa SDR17", "电熔旁通鞍型（SDR11）", "橡胶板止回阀"],
        "尺寸规格": ["32x2.3", "63x3.8", "90x63", "DN50"],
        "物料描述": ["PE100给水直管黑色 dn32 5.8M", "PE100给水直管黑色 dn63 5.8M", "电熔旁通鞍型(PE配件) dn90×63", "橡胶板止回阀 H44X-10Q/16Q DN50"],
        "Weight": [0.2000, 0.6596, 1.7472, 10.8000],
        "Pcs_Carton": [1, 1, 12, 1],
        "L": [5.8, 5.8, 0.56, 0.0], "W": [0.0, 0.0, 0.42, 0.0], "H": [0.0, 0.0, 0.33, 0.0],
        "CBM": [0.0, 0.0, 0.077616, 0.0]
    })

if 'base_price_db' not in st.session_state:
    st.session_state.base_price_db = pd.DataFrame({
        "SAP号": ["8010034798", "8010031990", "8010041365", "8060020258"],
        "基准价_RMB": [5.20, 18.50, 45.00, 180.00],
        "基准价_USD": [0.72, 2.56, 6.23, 24.93]
    })

if 'pi_cart' not in st.session_state:
    st.session_state.pi_cart = []


# --- 4. 主界面布局与外贸配置面板 ---
st.title("联塑外贸智能PI报价与利润精算平台 🚀")
st.markdown("---")

# 侧边栏：配置参数与表格上传
with st.sidebar:
    st.header("📂 数据源与汇率配置")
    
    # 汇率与加价策略精算
    usd_rate = st.number_input("实时美金汇率 (RMB -> USD)", min_value=1.0, max_value=15.0, value=7.22, step=0.01)
    profit_margin = st.slider("期望外贸毛利率 (%)", min_value=0, max_value=100, value=15, step=1)
    
    st.markdown("---")
    st.subheader("上传联塑官方内销/字典表")
    uploaded_file = st.file_uploader("支持管材、管件或阀门Excel表", type=["xlsx", "xls"])
    
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            parsed_df = smart_parse_dictionary(df)
            if parsed_df is not None:
                st.session_state.product_dictionary = parsed_df
                st.success("🎉 联塑表格智能解析成功！")
            else:
                st.warning("未能从表格中解析出有效行，请检查表头字段。")
        except Exception as e:
            st.error(f"解析出错，请检查格式: {e}")

# 页面主要展示：当前的产品字典数据库
st.subheader("📦 当前系统支持的联塑产品数据库")
st.dataframe(st.session_state.product_dictionary, use_container_width=True)


# --- 5. 交互式精算与模拟报价工作台 ---
st.markdown("---")
st.subheader("💡 智能外贸报价与 PI 模拟计算")

col1, col2, col3 = st.columns(3)
with col1:
    selected_sap = st.selectbox("选择要报价的联塑产品 (SAP号)", st.session_state.product_dictionary["SAP号"].tolist())
with col2:
    quantity = st.number_input("订货数量 (QTY)", min_value=1, value=100, step=1)
with col3:
    discount = st.number_input("工厂折扣率 (如0.65代表65折)", min_value=0.1, max_value=2.0, value=1.0, step=0.05)

# 根据选择的SAP号，捞出对应的数据进行外贸倒推计算
prod_info = st.session_state.product_dictionary[st.session_state.product_dictionary["SAP号"] == selected_sap].iloc[0]
price_info = st.session_state.base_price_db[st.session_state.base_price_db["SAP号"] == selected_sap]

# 如果基础价格表有就用价格表，没有就给个默认底价
base_rmb = price_info.iloc[0]["基准价_RMB"] if not price_info.empty else 10.0
factory_cost = base_rmb * discount
target_usd_price = (factory_cost / (1 - profit_margin / 100)) / usd_rate
total_amount_usd = target_usd_price * quantity
total_cbm = float(prod_info["CBM"]) * (quantity / int(prod_info["Pcs_Carton"])) if int(prod_info["Pcs_Carton"]) > 0 else 0.0

# 结果高亮展示
st.info(f"**产品解析：** {prod_info['物料描述']} | **单件重量：** {prod_info['Weight']} kg")

stat1, stat2, stat3 = st.columns(3)
stat1.metric("建议外贸保本美金单价 (FOB)", f"${target_usd_price:.3f}")
stat2.metric("该项总金额 (Total USD)", f"${total_amount_usd:.2f}")
stat3.metric("预估总体积 (Total CBM)", f"{total_cbm:.3f} m³")

if st.button("➕ 将此项加入临时 PI 报价单"):
    st.session_state.pi_cart.append({
        "SAP号": selected_sap,
        "描述": prod_info['物料描述'],
        "数量": quantity,
        "美金单价": round(target_usd_price, 3),
        "总金额": round(total_amount_usd, 2),
        "总CBM": round(total_cbm, 4)
    })
    st.success("已成功添加！")

# 渲染当前的临时报价单
if st.session_state.pi_cart:
    st.markdown("---")
    st.subheader("📋 实时模拟 Proforma Invoice 预览")
    cart_df = pd.DataFrame(st.session_state.pi_cart)
    st.dataframe(cart_df, use_container_width=True)
    
    st.write(f"**合计美金总额：** ${cart_df['总金额'].sum():,.2f} USD  |  **预计总立方数：** {cart_df['总CBM'].sum():.3f} CBM")
    if st.button("🧹 清空当前报价单"):
        st.session_state.pi_cart = []
        st.rerun()
