from __future__ import annotations

from datetime import datetime
import hashlib
import pandas as pd
import streamlit as st

from auth import authenticate, ensure_default_admin, hash_password
from database import (
    create_or_update_user,
    delete_product,
    get_categories,
    get_db_status,
    get_database_backend_name,
    init_db,
    list_users,
    load_products,
    save_quote_history,
    save_uploaded_images,
    set_user_active,
    upsert_products,
)
from exporters import export_quote_excel, export_quote_pdf, get_pdf_font_status
from quote_engine import PriceRule, build_quote_items, quote_summary

# 一键初始化数据库
init_db()
ensure_default_admin()

# -----------------------------------------------------------------------------
# 🌟 电商级淘宝风高级样式重写 (CSS)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* 页面全局底色与大容器优化 */
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem;
        max-width: 1440px;
    }
    /* 淘宝风商品卡片样式 */
    .product-card {
        background-color: #ffffff;
        border: 1px solid #eef1f6;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        transition: all 0.3s ease;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        height: 100%;
    }
    .product-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 20px rgba(255, 80, 0, 0.12);
        border-color: #ff5000;
    }
    .product-img-container {
        width: 100%;
        height: 160px;
        background-color: #f8f8f8;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        margin-bottom: 12px;
    }
    .product-img-container img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
    }
    .product-title {
        font-size: 15px;
        font-weight: 600;
        color: #333333;
        line-height: 1.4;
        height: 42px;
        overflow: hidden;
        margin-bottom: 8px;
    }
    .product-meta {
        font-size: 12px;
        color: #888888;
        margin-bottom: 4px;
    }
    .product-price {
        font-size: 18px;
        font-weight: bold;
        color: #ff5000; /* 淘宝经典橙红 */
        margin-top: 8px;
        margin-bottom: 12px;
    }
    /* 悬浮购物车面板 */
    .cart-summary-box {
        background: linear-gradient(135deg, #fff7f2 0%, #ffffff 100%);
        border: 1px solid #ffe8db;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(255, 80, 0, 0.05);
        margin-bottom: 25px;
    }
    /* 按钮美化 */
    div.stButton > button:first-child {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# 会话状态初始化 (Session States)
# -----------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user_role" not in st.session_state:
    st.session_state["user_role"] = "user"
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "cart" not in st.session_state:
    st.session_state["cart"] = {}  # 格式: {sap_id: quantity}
if "export_files" not in st.session_state:
    st.session_state["export_files"] = {}

# -----------------------------------------------------------------------------
# 🔐 第一层：安全登录大门
# -----------------------------------------------------------------------------
if not st.session_state["authenticated"]:
    col_l, col_c, col_r = st.columns([1, 1.5, 1])
    with col_c:
        st.write("")
        st.write("")
        st.title("LESSO 联塑外贸智能精算平台 🚀")
        with st.form("login_form", clear_on_submit=False):
            st.subheader("🛍️ 业务员登录中心")
            u = st.text_input("用户名 / Username")
            p = st.text_input("密码 / Password", type="password")
            submitted = st.form_submit_with_submit_button("安全登录 Sign In")
            if submitted:
                user = authenticate(u, p)
                if user:
                    st.session_state["authenticated"] = True
                    st.session_state["user_role"] = user["role"]
                    st.session_state["username"] = user["username"]
                    st.success(f"欢迎回来，{u}！正在加载您的淘宝风工作台...")
                    st.rerun()
                else:
                    st.error("账户名或密码错误，请检查您的 Secrets 配置。")
    st.stop()

# -----------------------------------------------------------------------------
# 🗂️ 核心导航：区分【淘宝旗舰店选单】与【后台数据清洗】
# -----------------------------------------------------------------------------
tabs = ["🛍️ 联塑选品旗舰店 (淘宝风)", "📊 购物车与精算成单", "⚙️ 管理员后台 (上传字典/清洗图片)"]
if st.session_state["user_role"] != "admin":
    tabs = ["🛍️ 联塑选品旗舰店 (淘宝风)", "📊 购物车与精算成单"]

selected_tab = st.sidebar.radio("系统功能导航", tabs)

# 退出登录按钮
if st.sidebar.button("🚪 退出当前账号"):
    st.session_state["authenticated"] = False
    st.rerun()

# 📊 全局调取 Supabase 数据
all_products = load_products()

# -----------------------------------------------------------------------------
# 🛍️ 第一板块：联塑选品旗舰店 (电商卡片流布局)
# -----------------------------------------------------------------------------
if selected_tab == "🛍️ 联塑选品旗舰店 (淘宝风)":
    st.title("🛒 LESSO 联塑产品智选旗舰店")
    st.caption("基于大数据的外贸商品卡片流，支持图片预览、一键添加、无感流转。")
    
    # 筛选大面板
    with st.expander("🔍 高级智能筛选面板", expanded=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            cats = ["全部类目"] + list(get_categories())
            selected_cat = st.selectbox("按产品大类筛选", cats)
        with f_col2:
            search_kw = st.text_input("输入物料描述/SAP号/规格 关键字搜索")
        with f_col3:
            price_sort = st.selectbox("价格排序", ["默认排序", "价格从低到高", "价格从高到低"])

    # 过滤数据
    display_df = all_products.copy()
    if selected_cat != "全部类目":
        display_df = display_df[display_df["category"] == selected_cat]
    if search_kw:
        display_df = display_df[
            display_df["sap"].str.contains(search_kw, case=False, na=False) |
            display_df["name"].str.contains(search_kw, case=False, na=False) |
            display_df["description"].str.contains(search_kw, case=False, na=False) |
            display_df["size"].str.contains(search_kw, case=False, na=False)
        ]
    
    if price_sort == "价格从低到高":
        display_df = display_df.sort_values(by="price", ascending=True)
    elif price_sort == "价格从高到低":
        display_df = display_df.sort_values(by="price", ascending=False)

    if display_df.empty:
        st.warning("📭 仓库里没有找到匹配的联塑产品，请前往后台上传 Excel 字典表。")
    else:
        # 🌟 核心：四列网格瀑布流（高仿电商前台）
        grid_columns = 4
        rows = [display_df.iloc[i:i+grid_columns] for i in range(0, len(display_df), grid_columns)]
        
        for row_data in rows:
            cols = st.columns(grid_columns)
            for idx, (_, item) in enumerate(row_data.iterrows()):
                with cols[idx]:
                    sap_id = item["sap"]
                    # 读取图片，没有就给默认占位图
                    img_url = item["image_url"] if pd.notna(item["image_url"]) and item["image_url"] else "https://via.placeholder.com/150?text=LESSO"
                    
                    # 渲染卡片的 HTML
                    st.markdown(
                        f"""
                        <div class="product-card">
                            <div class="product-img-container">
                                <img src="{img_url}">
                            </div>
                            <div class="product-title">{item['description'] or item['name']}</div>
                            <div class="product-meta">🔢 SAP: {sap_id}</div>
                            <div class="product-meta">📐 规格: {item['size'] or '标准'}</div>
                            <div class="product-meta">📦 装箱: {int(item['packing_pcs'] or 1)} Pcs/Ctn</div>
                            <div class="product-price">${float(item['price'] or 0):.2f} <span style='font-size:12px; color:#999;'>基准价</span></div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    # 配合卡片使用的表单级“加入购物车”按钮，防止刷新页面
                    with st.form(key=f"btn_form_{sap_id}", clear_on_submit=False):
                        qty = st.number_input("订购数量", min_value=1, value=100, step=10, key=f"qty_{sap_id}")
                        if st.form_submit_with_submit_button("🛒 加入报价购物车", use_container_width=True):
                            current_cart = st.session_state["cart"]
                            current_cart[sap_id] = current_cart.get(sap_id, 0) + qty
                            st.session_state["cart"] = current_cart
                            st.toast(f"已成功添加 {qty} 件至购物车！", icon="✅")

# -----------------------------------------------------------------------------
# 📊 第二板块：购物车、精算器与一键导出合集
# -----------------------------------------------------------------------------
elif selected_tab == "📊 购物车与精算成单":
    st.title("📊 外贸购物车与精算控制台")
    
    cart = st.session_state["cart"]
    if not cart:
        st.info("您的购物车空空如也，请先去旗舰店挑几款联塑产品吧！")
        st.stop()
        
    # 从总产品库中提取被挑中的商品信息
    selected_saps = list(cart.keys())
    cart_products = all_products[all_products["sap"].isin(selected_saps)].copy()
    cart_products["quantity"] = cart_products["sap"].map(cart)

    # 1. 顶部精算面板：汇率、调价策略
    st.subheader("💡 国际贸易精算调节阀")
    c1, c2, c3 = st.columns(3)
    with c1:
        calc_mode = st.selectbox("调价模式策略", ["原价", "加点", "打折"])
    with c2:
        calc_percent = st.number_input("百分比 (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    with c3:
        currency_info = st.text_input("计价币种及备注", "USD (FOB China)")

    # 应用调价引擎
    rule = PriceRule(mode=calc_mode, percent=calc_percent)
    quote_items_df = build_quote_items(cart_products, rule)
    summary = quote_summary(quote_items_df)

    # 🌟 2. 淘宝风：合集数据总计面板
    st.markdown(
        f"""
        <div class="cart-summary-box">
            <h3 style='margin-top:0; color:#ff5000;'>📋 预选产品合集总计 (PI Summary)</h3>
            <div style='display: flex; justify-content: space-between; flex-wrap: wrap;'>
                <div style='font-size: 16px; margin-right: 25px;'>🔢 选定品类总数: <b>{summary['total_items']} 款</b></div>
                <div style='font-size: 16px; margin-right: 25px;'>📦 订货件数总计: <b>{int(summary['total_quantity'])} Pcs</b></div>
                <div style='font-size: 16px; margin-right: 25px;'>📐 预计总体积: <span style='color:#1f4e78; font-weight:bold;'>{float(summary['total_volume']):.3f} CBM</span></div>
                <div style='font-size: 20px; color: #ff5000;'>💰 最终美金总额: <b>${float(summary['total_amount']):,.2f} USD</b></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 3. 详细购物车清单与修改
    st.subheader("🛒 已选商品明细微调")
    for idx, row in quote_items_df.iterrows():
        with st.container():
            col_img, col_txt, col_edit = st.columns([1, 4, 2])
            with col_img:
                st.image(row["image_url"] if row["image_url"] else "https://via.placeholder.com/80?text=LESSO", width=70)
            with col_txt:
                st.markdown(f"**{row['description'] or row['name']}**")
                st.caption(f"SAP: {row['sap']} | 单个体积: {row['packing_volume']} CBM | 基准价: ${row['base_price']:.2f}")
                st.markdown(f"精算后单价: <span style='color:#ff5000; font-weight:bold;'>${row['quote_price']:.2f}</span> | 小计: **${row['amount']:.2f}**", unsafe_allow_html=True)
            with col_edit:
                # 允许在购物车内微调数量或删除
                new_q = st.number_input("调整数量", min_value=0, value=int(row["quantity"]), key=f"edit_q_{row['sap']}")
                if new_q != int(row["quantity"]):
                    if new_q == 0:
                        del st.session_state["cart"][row["sap"]]
                    else:
                        st.session_state["cart"][row["sap"]] = new_q
                    st.rerun()
            st.markdown("---")

    # 🌟 4. 一键导出符合外贸标准的报价合集 (调用 exporters.py)
    st.subheader("📥 国际商务单据一键成单导出")
    customer_name = st.text_input("买家客户名称 (Customer Name)", "Global Trade Client")
    quote_no = st.text_input("系统自动生成单号", f"PI-LESSO-{datetime.now().strftime('%Y%m%d%H%M')}")

    # 将数据包准备好
    items_list = quote_items_df.to_dict(orient="records")
    
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        if st.button("🚀 编译 中文 Excel", use_container_width=True):
            st.session_state["export_files"]["excel_zh"] = export_quote_excel(items_list, customer_name, quote_no, currency_info, lang="zh")
            st.toast("中文 Excel 编译成功！")
    with g2:
        if st.button("🚀 编译 英文 Excel", use_container_width=True):
            st.session_state["export_files"]["excel_en"] = export_quote_excel(items_list, customer_name, quote_no, currency_info, lang="en")
            st.toast("英文 Excel 编译成功！")
    with g3:
        if st.button("🚀 编译 中文 PDF", use_container_width=True):
            st.session_state["export_files"]["pdf_zh"] = export_quote_pdf(items_list, customer_name, quote_no, currency_info, lang="zh")
            st.toast("中文 PDF 编译成功！")
    with g4:
        if st.button("🚀 编译 英文 PDF", use_container_width=True):
            st.session_state["export_files"]["pdf_en"] = export_quote_pdf(items_list, customer_name, quote_no, currency_info, lang="en")
            st.toast("英文 PDF 编译成功！")

    # 真正触发浏览器下载
    st.write("")
    d1, d2, d3, d4 = st.columns(4)
    ef = st.session_state["export_files"]
    with d1:
        if "excel_zh" in ef:
            st.download_button("💾 下载中文 Excel", data=ef["excel_zh"], file_name=f"{quote_no}_中文报价.xlsx", use_container_width=True)
    with d2:
        if "excel_en" in ef:
            st.download_button("💾 下载英文 Excel", data=ef["excel_en"], file_name=f"{quote_no}_Quotation.xlsx", use_container_width=True)
    with d3:
        if "pdf_zh" in ef:
            st.download_button("💾 下载中文 PDF", data=ef["pdf_zh"], file_name=f"{quote_no}_中文报价.pdf", use_container_width=True)
    with d4:
        if "pdf_en" in ef:
            st.download_button("💾 下载英文 PDF", data=ef["pdf_en"], file_name=f"{quote_no}_Quotation.pdf", use_container_width=True)

    if st.button("🧹 清空购物车，开始下一单"):
        st.session_state["cart"] = {}
        st.session_state["export_files"] = {}
        st.rerun()

# -----------------------------------------------------------------------------
# ⚙️ 第三板块：管理员后台 (承接原版系统的 Excel 智能清洗与管理功能)
# -----------------------------------------------------------------------------
elif selected_tab == "⚙️ 管理员后台 (上传字典/清洗图片)":
    st.title("⚙️ 系统大本营数据管理后台")
    
    st.subheader("📂 批量导入联塑 Excel 字典文档")
    uploaded_file = st.file_uploader("请在此处拖入联塑官方管材/阀门原始 Excel 清单", type=["xlsx", "xls"])
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            st.write("📂 成功抓取原始表格，正在进行智能映射清洗...")
            # 调用原版 database.py 里的高容错清洗写入逻辑
            upsert_products(df)
            st.success("🎉 文档自动解析完毕！所有字段及体积已成功同步到 Supabase 数据库！")
        except Exception as e:
            st.error(f"解析出错，请确认表头字段是否包含物料号或规格: {e}")

    st.write("---")
    st.subheader("📦 当前云端大仓库所有货品存量一览")
    st.dataframe(all_products, use_container_width=True)
