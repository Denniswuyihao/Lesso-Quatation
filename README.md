import streamlit as st
import pandas as pd
import numpy as np

# ==========================================
# 1. 网页基础配置与全局样式注入
# ==========================================
st.set_page_config(
    page_title="联塑外贸智能PI报价与利润精算平台", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# 自定义一些高质感的外贸风 CSS 样式
st.markdown("""
    <style>
    .main-title { font-size: 32px; font-weight: 700; color: #0C2340; margin-bottom: 5px; }
    .sub-title { font-size: 14px; color: #666; margin-bottom: 25px; }
    .metric-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #0056b3; }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 2. 核心数据清洗与多模态智能表头解析引擎
# ==========================================
def find_header_and_read(file):
    """
    鲁棒性增强：自动向下扫描前20行，直至抓取到包含外贸核心字段的行作为真实表头。
    完美解决联塑表格顶部带有合并单元格、公司大名称或多余空行的问题。
    """
    try:
        # 先以无表头模式读取进行结构嗅探
        if file.name.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(file, header=None)
        else:
            df_raw = pd.read_csv(file, header=None)
        
        header_row_idx = 0
        for idx, row in df_raw.head(20).iterrows():
            row_str = row.astype(str).str.strip().tolist()
            # 匹配经典的联塑表头关键字
            if any(any(k in s.upper() for k in ['SAP', '物料号', 'CODE', 'PRODUCT', 'DESCRIPTION', '规格', '尺寸']) for s in row_str if pd.notna(s)):
                header_row_idx = idx
                break
        
        # 指针复位，带着正确的行数重新完整读取
        file.seek(0)
        if file.name.endswith(('.xlsx', '.xls')):
            df_correct = pd.read_excel(file, skiprows=header_row_idx)
        else:
            df_correct = pd.read_csv(file, skiprows=header_row_idx)
        return df_correct
    except Exception as e:
        st.error(f"文件预解析失败，请检查格式: {str(e)}")
        return pd.DataFrame()

def smart_parse_dictionary(df):
    """
    多模态数据标准化：将标准纵向管材/管件表，或横向多变体的阀门表统一解构。
    """
    if df is None or df.empty:
        return None
        
    cleaned_rows = []
    df.columns = df.columns.astype(str).str.strip()
    cols = df.columns.tolist()
    
    # 拓扑嗅探：是否为阀门类并排排版（检查是否含有'I型'、'II型'或重复的'物料号'）
    is_valve_layout = any("型" in c for c in cols) or "物料号" in cols
    
    if is_valve_layout:
        # 阀门特殊排版降维处理
        for idx, row in df.iterrows():
            prod_name = str(row.get("产品名称", "阀门产品")) if pd.notna(row.get("产品名称")) else "阀门产品"
            spec = str(row.get("规格", row.get("规格(mm)", ""))) if pd.notna(row.get("规格", row.get("规格(mm)"))) else ""
            
            for col_idx, col_name in enumerate(cols):
                if "物料号" in col_name and pd.notna(row.iloc[col_idx]):
                    sap_code = str(row.iloc[col_idx]).split('.')[0].strip()
                    if not sap_code or sap_code.lower() in ['nan', '/', '', 'none']: 
                        continue
                        
                    price = 0.0
                    weight = 0.0
                    try:
                        if col_idx + 1 < len(cols) and pd.notna(row.iloc[col_idx + 1]): 
                            price = float(row.iloc[col_idx + 1])
                        if col_idx + 2 < len(cols) and pd.notna(row.iloc[col_idx + 2]): 
                            weight = float(row.iloc[col_idx + 2])
                    except:
                        pass
                        
                    cleaned_rows.append({
                        "SAP号": sap_code, "产品名称": prod_name, "尺寸规格": spec, "物料描述": f"{prod_name} {spec}",
                        "Weight": weight, "Pcs_Carton": 1, "L": 0.0, "W": 0.0, "H": 0.0, "CBM": 0.0
                    })
    else:
        # 兼容管材、管件的标准纵向列表（自动映射中英文表头）
        sap_col = next((c for c in cols if any(k in c.upper() for k in ["SAP", "物料号", "CODE"])), None)
        name_col = next((c for c in cols if any(k in c for k in ["名称", "NAME"])), None)
        desc_col = next((c for c in cols if any(k in c for k in ["描述", "DESC"])), None)
        size_col = next((c for c in cols if any(k in c for k in ["SIZE", "规格", "尺寸"])), None)
        weight_col = next((c for c in cols if any(k in c for k in ["WEIGHT", "重量"])), None)
        pcs_col = next((c for c in cols if any(k in c for k in ["PCS", "装箱", "CARTON", "每箱"])), None)
        
        if not sap_col:
            return None
            
        for idx, row in df.iterrows():
            sap_code = str(row.get(sap_col, "")).split('.')[0].strip()
            if not sap_code or sap_code.lower() in ['nan', '', '/', 'none']: 
                continue
            
            # 安全抓取长宽高与体积
            l_val = float(row.get("L", 0)) if pd.notna(row.get("L", 0)) and isinstance(row.get("L", 0), (int, float)) else 0.0
            w_val = float(row.get("W", 0)) if pd.notna(row.get("W", 0)) and isinstance(row.get("W", 0), (int, float)) else 0.0
            h_val = float(row.get("H", 0)) if pd.notna(row.get("H", 0)) and isinstance(row.get("H", 0), (int, float)) else 0.0
            cbm_val = float(row.get("CBM", 0)) if pd.notna(row.get("CBM", 0)) and isinstance(row.get("CBM", 0), (int, float)) else 0.0
            
            # 如果表格没有现成CBM，系统通过包装尺寸自动计算
            if cbm_val == 0 and (l_val * w_val * h_val) > 0:
                if l_val > 10:  # 智能判定：数值较大代表是毫米(mm)单位，需除以1e9转换为立方米
                    cbm_val = (l_val * w_val * h_val) / 1e9
                else:          # 数值小代表已经是米(M)单位
                    cbm_val = l_val * w_val * h_val
                    
            cleaned_rows.append({
                "SAP号": sap_code,
                "产品名称": str(row.get(name_col, "")) if name_col else "",
                "尺寸规格": str(row.get(size_col, "")) if size_col else "",
                "物料描述": str(row.get(desc_col, row.get(name_col, ""))) if desc_col else str(row.get(name_col, "")),
                "Weight": float(row.get(weight_col, 0.0)) if pd.notna(row.get(weight_col, 0.0)) else 0.0,
                "Pcs_Carton": int(row.get(pcs_col, 1)) if pd.notna(row.get(pcs_col, 1)) and str(row.get(pcs_col)).isdigit() else 1,
                "L": l_val, "W": w_val, "H": h_val, "CBM": round(cbm_val, 6)
            })
            
    return pd.DataFrame(cleaned_rows) if cleaned_rows else None


# ==========================================
# 3. 全局状态初始化（含高保真首发模拟底座数据）
# ==========================================
if 'product_dictionary' not in st.session_state:
    st.session_state.product_dictionary = pd.DataFrame({
        "SAP号": ["8010034798", "8010031990", "8010041365", "8060020258"],
        "产品名称": ["PE给水管", "PE给水管", "电熔旁通鞍型", "橡胶板止回阀"],
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


# ==========================================
# 4. 侧边栏：多币种财务控制与无损模板导入
# ==========================================
st.sidebar.markdown("<h3 style='color:#0C2340;'>⚙️ 全局财务控制中心</h3>", unsafe_allow_html=True)
exchange_rate = st.sidebar.number_input("实时汇率 (USD/CNY)", min_value=1.0, max_value=15.0, value=7.22, step=0.01)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔄 联塑原始报表无损导入")
st.sidebar.caption("完美适配管材、管件以及并排阀门明细表")

uploaded_dict = st.sidebar.file_uploader("1️⃣ 导入【产品大全/阀门明细表】", type=["xlsx", "xls", "csv"])
uploaded_price = st.sidebar.file_uploader("2️⃣ 导入【最新基准价核算表】", type=["xlsx", "xls", "csv"])

# 处理字典文件上传
if uploaded_dict:
    raw_df = find_header_and_read(uploaded_dict)
    parsed_df = smart_parse_dictionary(raw_df)
    if parsed_df is not None and not parsed_df.empty:
        st.session_state.product_dictionary = parsed_df
        st.sidebar.success(f"✅ 成功智能化解构并加载 {len(parsed_df)} 条产品SKU！")
    else:
        st.sidebar.error("❌ 无法提取有效列，请确认表格中是否包含 SAP号/物料号 等核心标志。")

# 处理基准价核算文件上传
if uploaded_price:
    p_df = find_header_and_read(uploaded_price)
    p_cols = p_df.columns.astype(str).str.strip().tolist()
    sap_col = next((c for c in p_cols if any(k in c.upper() for k in ["SAP", "物料号", "CODE"])), None)
    rmb_col = next((c for c in p_cols if any(k in c for k in ["RMB", "人民币", "基准价", "单价", "PRICE"] if "USD" not in k.upper())), None)
    usd_col = next((c for c in p_cols if "USD" in c.upper() or "美金" in c or "美元" in c), None)
    
    if sap_col:
        p_df = p_df.rename(columns={sap_col: "SAP号"})
        if rmb_col: p_df = p_df.rename(columns={rmb_col: "基准价_RMB"})
        if usd_col: p_df = p_df.rename(columns={usd_col: "基准价_USD"})
        if "基准价_RMB" not in p_df.columns: p_df["基准价_RMB"] = np.nan
        if "基准价_USD" not in p_df.columns: p_df["基准价_USD"] = np.nan
        
        st.session_state.base_price_db = p_df[["SAP号", "基准价_RMB", "基准价_USD"]].dropna(subset=["SAP号"])
        st.sidebar.success("✅ 最新内部基准价格库注入成功！")


# ==========================================
# 5. 主界面多功能工作舱
# ==========================================
st.markdown("<div class='main-title'>💧 LIANSU 联塑外贸智能PI报价与精算系统</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>全自适应容错架构 ｜ 自由定义单品利润率倒推 ｜ 实时双币种沉淀精算看板</div>", unsafe_allow_html=True)

tabs = st.tabs(["🔍 4维检索与自由可控定价", "📄 联塑标准 PI 生成仓", "📈 内部利润提现核算看板"])

# ------------------------------------------
# TAB 1: 4维检索与利润点驱动控制台
# ------------------------------------------
with tabs[0]:
    st.subheader("🕵️‍♂️ 4维精准交叉检索仓")
    s1, s2, s3 = st.columns(3)
    with s1: search_cn = st.text_input("🇨🇳 产品名称/描述关键字 (如: PE / 鞍型 / 阀门)")
    with s2: search_size = st.text_input("📏 尺寸规格 (如: 32x2.3 / dn90 / DN50)")
    with s3: search_sap = st.text_input("🔢 唯一 SAP 编码直接定位")

    # 执行模糊交叉过滤
    df_res = st.session_state.product_dictionary.copy()
    if search_cn: 
        df_res = df_res[df_res['物料描述'].str.contains(search_cn, case=False, na=False) | df_res['产品名称'].str.contains(search_cn, case=False, na=False)]
    if search_size: 
        df_res = df_res[df_res['尺寸规格'].str.contains(search_size, case=False, na=False)]
    if search_sap: 
        df_res = df_res[df_res['SAP号'].str.contains(search_sap, na=False)]

    # 动态关联左侧导入的内部成本价
    df_res = pd.merge(df_res, st.session_state.base_price_db, on="SAP号", how="left")
    
    st.markdown("##### 💡 联动过滤匹配到的产品及包装底座信息：")
    st.dataframe(df_res[["SAP号", "产品名称", "尺寸规格", "物料描述", "Weight", "Pcs_Carton", "CBM", "基准价_RMB", "基准价_USD"]], use_container_width=True)

    st.markdown("---")
    st.subheader("⚙️ 自由定义利润点 / 最终售价倒推台")
    if not df_res.empty:
        col_sap, col_qty, col_mode, col_calc = st.columns(4)
        with col_sap:
            selected_sap = st.selectbox("1. 选定目标 SAP 编码", df_res['SAP号'].unique())
        
        tgt_row = df_res[df_res['SAP号'] == selected_sap].iloc[0]
        has_base_price = not pd.isna(tgt_row['基准价_USD']) and tgt_row['基准价_USD'] > 0
        cost_usd = float(tgt_row['基准价_USD']) if has_base_price else 0.0
        cost_rmb = float(tgt_row['基准价_RMB']) if has_base_price else 0.0
        
        with col_qty:
            input_qty = st.number_input("2. 输入采购数量 (QTY)", min_value=1, value=1000, step=100)
        with col_mode:
            pricing_strategy = st.radio("3. 选择定价驱动模式", ["🎯 自由定义目标利润点 (%)", "💰 直接指定对外销售最终价"])
            
        with col_calc:
            if pricing_strategy == "🎯 自由定义目标利润点 (%)":
                if not has_base_price:
                    st.warning("⚠️ 该产品缺少内部基准成本价，请切换至直接售价模式手工补价。")
                    user_margin = 0.0; input_sales_usd = 0.0; input_sales_rmb = 0.0
                else:
                    # 单品利润点输入
                    user_margin = st.number_input("设定该单品利润点 (%)", min_value=-50.0, max_value=95.0, value=15.0, step=1.0)
                    # 经典外贸毛利倒推公式：售价 = 成本 / (1 - 利润率)
                    input_sales_usd = cost_usd / (1 - (user_margin / 100.0))
                    input_sales_rmb = input_sales_usd * exchange_rate
                    st.success(f"自动算出售价: ${input_sales_usd:.4f}")
            else:
                input_sales_usd = st.number_input("直接输入对外美金单价 (USD)", min_value=0.0, value=float(cost_usd * 1.15) if has_base_price else 0.0, format="%.4f")
                input_sales_rmb = st.number_input("对照当前人民币单价 (RMB)", min_value=0.0, value=float(input_sales_usd * exchange_rate), format="%.4f")
                if input_sales_usd > 0 and has_base_price:
                    user_margin = (input_sales_usd - cost_usd) / input_sales_usd * 100
                else:
                    user_margin = 15.0
                    if input_sales_usd > 0 and cost_usd == 0:
                        cost_usd = input_sales_usd / 1.15; cost_rmb = input_sales_rmb / 1.15

        st.markdown(f"📊 **单品实时透视**：当前真实毛利率：`{user_margin:.2f}%` ｜ 单个美金利润留存：`${(input_sales_usd - cost_usd):.4f}`")

        if st.button("➕ 锁定当前利润，追加至形式发票 (Add to PI)", use_container_width=True):
            pcs_per_carton = float(tgt_row['Pcs_Carton']) if pd.notna(tgt_row['Pcs_Carton']) and float(tgt_row['Pcs_Carton']) > 0 else 1.0
            total_boxes = input_qty / pcs_per_carton
            total_cbm = total_boxes * (float(tgt_row['CBM']) if pd.notna(tgt_row['CBM']) else 0.0)
            total_weight = input_qty * (float(tgt_row['Weight']) if pd.notna(tgt_row['Weight']) else 0.0)
            
            cart_item = {
                "Item No.": len(st.session_state.pi_cart) + 1, "SAP Code": selected_sap, "Description": str(tgt_row['物料描述']), "QTY\n(PC)": input_qty,
                "Unit Price (USD)": round(input_sales_usd, 4), "Amount (USD)": round(input_sales_usd * input_qty, 2), "Remark": f"Size: {tgt_row['尺寸规格']}",
                "cost_usd_total": cost_usd * input_qty, "cost_rmb_total": cost_rmb * input_qty, "sales_rmb_total": input_sales_rmb * input_qty,
                "Calculated_Boxes": total_boxes, "Calculated_CBM": total_cbm, "Calculated_Weight": total_weight
            }
            st.session_state.pi_cart.append(cart_item)
            st.success("✅ 该笔报价已成功加入发票池！可前往第二页查看和下载。")
    else:
        st.warning("暂无匹配产品，请调整上方的检索词。")

# ------------------------------------------
# TAB 2: 联塑标准 PI 生成与无损导出
# ------------------------------------------
with tabs[1]:
    st.subheader("📄 联塑标准 Proforma Invoice (合规外贸单据)")
    if not st.session_state.pi_cart:
        st.info("发票池内尚无数据，请先在第一页选定产品、调配好利润后追加至发票。")
    else:
        df_pi = pd.DataFrame(st.session_state.pi_cart)
        pi_cols = ["Item No.", "SAP Code", "Description", "QTY\n(PC)", "Unit Price (USD)", "Amount (USD)", "Remark"]
        
        st.markdown("#### **LIANSU GROUP COMPANY LIMITED**")
        st.caption("Address: Liansu Industrial Area, Longjiang Town, Shunde, Foshan, Guangdong, China")
        st.markdown("---")
        st.dataframe(df_pi[pi_cols], use_container_width=True)
        
        # 实时包装物流参数精算汇总
        l1, l2, l3, l4 = st.columns(4)
        l1.metric("💰 发票总金额 (Total Amount)", f"${df_pi['Amount (USD)'].sum():,.2f} USD")
        l2.metric("🐳 预估总容量 (Total CBM)", f"{df_pi['Calculated_CBM'].sum():,.4f} CBM")
        l3.metric("⚖️ 预估总重量 (Total Weight)", f"{df_pi['Calculated_Weight'].sum():,.2f} KG")
        l4.metric("📦 累计总箱数 (Total Boxes)", f"{df_pi['Calculated_Boxes'].sum():,.1f} CTNS")
        
        # 导出标准的PI表格CSV
        st.download_button(
            label="📥 导出为联塑标准 PI 格式电子表格 (.CSV)",
            data=df_pi[pi_cols].to_csv(index=False).encode('utf-8-sig'),
            file_name="LIANSU_PROFORMA_INVOICE.csv", mime="text/csv", use_container_width=True
        )

# ------------------------------------------
# TAB 3: 内部双币种精算与利润提现分析
# ------------------------------------------
with tabs[2]:
    st.subheader("📈 内部利润提现与双币精算控制台 (内部核算专用)")
    if not st.session_state.pi_cart:
        st.info("尚未录入任何开单报价，利润看板暂无分析数据。")
    else:
        df_profit = pd.DataFrame(st.session_state.pi_cart)
        
        t_sales_usd = df_profit['Amount (USD)'].sum()
        t_cost_usd = df_profit['cost_usd_total'].sum()
        t_profit_usd = t_sales_usd - t_cost_usd
        t_margin_usd = (t_profit_usd / t_sales_usd) if t_sales_usd > 0 else 0.0
        
        t_sales_rmb = df_profit['sales_rmb_total'].sum()
        t_cost_rmb = df_profit['cost_rmb_total'].sum()
        t_profit_rmb = t_sales_rmb - t_cost_rmb
        t_margin_rmb = (t_profit_rmb / t_sales_rmb) if t_sales_rmb > 0 else 0.0
        
        f1, f2 = st.columns(2)
        with f1:
            st.markdown("<div class='metric-card'><h4>🇺🇸 美金盘核算明细</h4>", unsafe_allow_html=True)
            st.metric("累计美金纯毛利", f"${t_profit_usd:,.2f}", f"整单平均美金利润点: {t_margin_usd:.2%}")
            st.markdown("</div>", unsafe_allow_html=True)
        with f2:
            st.markdown("<div class='metric-card' style='border-left-color:#28a745;'><h4>🇨🇳 人民币盘核算明细</h4>", unsafe_allow_html=True)
            st.metric("累计人民币纯毛利", f"¥{t_profit_rmb:,.2f}", f"整单平均人民币利润点: {t_margin_rmb:.2%}")
            st.markdown("</div>", unsafe_allow_html=True)
            
        st.markdown("---")
        st.markdown("##### 🕵️‍♂️ 逐行自定义利润沉淀穿透分析（高保真还原内部报价单提取逻辑）")
        
        df_profit['行美金利润点(%)'] = round(((df_profit['Amount (USD)'] - df_profit['cost_usd_total']) / df_profit['Amount (USD)']) * 100, 2)
        df_profit['行人民币利润点(%)'] = round(((df_profit['sales_rmb_total'] - df_profit['cost_rmb_total']) / df_profit['sales_rmb_total'] * 100), 2)
        
        st.dataframe(
            df_profit[["SAP Code", "Description", "QTY\n(PC)", "Unit Price (USD)", "Amount (USD)", "行美金利润点(%)", "sales_rmb_total", "行人民币利润点(%)"]], 
            use_container_width=True
        )
        
        if st.button("🗑️ 清空当前全单数据，重新开立新单", use_container_width=True):
            st.session_state.pi_cart = []
            st.rerun()
