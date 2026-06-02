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

st.set_page_config(page_title="联塑外贸智能PI报价与利润精算平台", layout="wide", page_icon="📦")

# 初始化数据库与默认管理员
init_db()
ensure_default_admin()

# 注入淘宝风及商务感兼具的简洁样式
st.markdown(
    """
    <style>
    .main .block-container { padding-top: 2rem !important; padding-bottom: 2rem; max-width: 1360px; }
    .stButton>button { border-radius: 4px; font-weight: 500; }
    .product-card { border: 1px solid #eef2f6; border-radius: 8px; padding: 12px; background: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.02); margin-bottom: 15px; }
    .product-price { color: #ff4d4f; font-size: 1.1rem; font-weight: bold; }
    </style>
    """,
    unsafe_allow_not_allowed=True,
)

# 会话状态初始化
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "role" not in st.session_state:
    st.session_state["role"] = "user"
if "cart" not in st.session_state:
    st.session_state["cart"] = {}  # {sap: quantity}
if "export_files" not in st.session_state:
    st.session_state["export_files"] = {}

# --- 登录界面 ---
if not st.session_state["authenticated"]:
    st.subheader("🔑 欢迎使用联塑外贸智能报价单系统")
    with st.form("login_form"):
        username = st.text_input("用户名", value="admin")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录系统", use_container_width=True)
        if submitted:
            user = authenticate(username, password)
            if user:
                st.session_state["authenticated"] = True
                st.session_state["username"] = user["username"]
                st.session_state["role"] = user["role"]
                st.success(f"欢迎回来，{username}！")
                st.rerun()
            else:
                st.error("用户名或密码不正确，或账户已被禁用。")
    st.stop()

# --- 顶栏导航与注销 ---
t1, t2 = st.columns([8, 2])
with t1:
    st.title("联塑外贸智能报价与一键 PI 生成平台 🚀")
with t2:
    st.write(f"👤 账号: `{st.session_state['username']}` ({st.session_state['role']})")
    if st.button("退出登录", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

# 建立标签页：工作台与管理员后台
tabs = ["💡 智能报价工作台", "⚙️ 系统管理后台"] if st.session_state["role"] == "admin" else ["💡 智能报价工作台"]
active_tab = st.sidebar.radio("功能导航", tabs)

# -----------------------------------------------------------------------------
# TAB 1: 智能报价工作台（包含一键导出 Excel / PDF 核心逻辑）
# -----------------------------------------------------------------------------
if active_tab.startswith("💡"):
    # 加载当前 Supabase 数据库内的所有联塑产品
    all_prods = load_products()
    
    st.subheader("🛒 第一步：挑选报价产品")
    if all_prods.empty:
        st.info("💡 当前云端数据库中还没有产品数据。请联系管理员前往『系统管理后台』上传联塑 Excel 字典表。")
    else:
        # 分类筛选与搜索
        cats = ["全部分类"] + get_categories()
        sc1, sc2 = st.columns([3, 7])
        with sc1:
            sel_cat = st.selectbox("产品分类筛选", cats)
        with sc2:
            search_q = st.text_input("输入 编码(SAP) / 名称 / 规格 模糊搜索产品")
            
        filtered = all_prods.copy()
        if sel_cat != "全部分类":
            filtered = filtered[filtered["category"] == sel_cat]
        if search_q.strip():
            q = search_q.strip().lower()
            filtered = filtered[
                filtered["sap"].str.lower().str.contains(q) |
                filtered["name"].str.lower().str.contains(q) |
                filtered["description"].str.lower().str.contains(q) |
                filtered["size"].str.lower().str.contains(q)
            ]
            
        st.write(f"🔍 已为您检索到 {len(filtered)} 款符合条件的联塑产品：")
        
        # --- 淘宝风产品展示网格 ---
        for idx, row in filtered.head(30).iterrows():
            sap = row["sap"]
            with st.container():
                st.markdown(f"""
                <div class="product-card">
                    <strong>【{row['name']}】</strong> 规格: <code>{row['size']}</code> | SAP号: <code>{sap}</code><br/>
                    <small style="color:#666;">描述: {row['description']}</small><br/>
                    单箱装率: {row['packing_pcs']} Pcs/Ctn | 单件体积: {row['packing_volume']} CBM | 单件重量: {row['weight']} kg
                </div>
                """, unsafe_allow_html=True)
                
                # 交互加入购物车
                cc1, cc2 = st.columns([3, 2])
                with cc1:
                    qty = st.number_input(f"订购数量 (SAP: {sap})", min_value=1, va
