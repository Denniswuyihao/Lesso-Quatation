import streamlit as st
import pandas as pd
import numpy as np

# 1. 网页基础配置
st.set_page_config(page_title="联塑外贸智能PI报价与利润精算平台", layout="wide", initial_sidebar_state="expanded")

# --- 2. 核心清洗引擎：智能解析价格表（支持单双币种自适应转换） ---
def smart_parse_price_db(df, current_exchange_rate):
    """
    智能解析基准价格表：
    1. 自动定位 SAP编码列
    2. 自动寻找 RMB 或 USD 价格列
    3. 如果缺少其中一个币种，自动利用当前汇率进行换算补全，防止系统报错
    """
    cleaned_rows = []
    cols = df.columns.astype(str).str.strip().tolist()
    
    # 动态模糊匹配表头
    sap_col = next((c for c in cols if any(k in c.upper() for k in ["SAP", "物料", "编码", "CODE", "NO"])), None)
    rmb_col = next((c for c in cols if any(k in c.upper() for k in ["RMB", "人民币", "基准价", "工厂", "EXW", "单价"]) and "USD" not in c.upper() and "美" not in c.upper()), None)
    usd_col = next((c for c in cols if any(k in c.upper() for k in ["USD", "美金", "美元", "FOB", "外币"])), None)
    
    if not sap_col:
        st.error("❌ 价格表解析失败：未能在表格中找到包含 'SAP' 或 '物料号' 的列，请检查首行表头！")
        return None
        
    for idx, row in df.iterrows():
        sap_code = str(row.get(sap_col, "")).split('.')[0].strip()
        if not sap_code or sap_code.lower() == 'nan' or sap_code == '/':
            continue
            
        # 提取人民币价格
        r_val = row.get(rmb_col, 0.0) if rmb_col else 0.0
        r_price = float(r_val) if pd.notna(r_val) and isinstance(r_val, (int, float)) else 0.0
        
        # 提取美金价格
        u_val = row.get(usd_col, 0.0) if usd_col else 0.0
        u_price = float(u_val) if pd.notna(u_val) and isinstance(u_val, (int, float)) else 0.0
        
        # 核心逻辑：单双币种自适应互转底座
        if r_price > 0 and u_price == 0:
            u_price = r_price / current_exchange_rate
        elif u_price > 0 and r_price == 0:
            r_price = u_price * current_exchange_rate
            
        cleaned_rows.append({
            "SAP号": sap_code,
            "基准价_RMB": round(r_price, 4),
            "基准价_USD": round(u_price, 4)
        })
        
    return pd.DataFrame(cleaned_rows) if cleaned_rows else None


# --- 核心清洗引擎：智能解析产品大全/阀门明细表 ---
def smart_parse_dictionary(df):
    cleaned_rows = []
    cols = df.columns.astype(str).str.strip().tolist()
    
    # 判断是否为阀门横向并排排版
    is_valve_layout = any("型" in c for c in cols) or "物料号" in cols
    
    if is_valve_layout:
        for idx, row in df.iterrows():
            prod_name = row.get("产品名称", "阀门产品")
            spec = row.get("规格", row.get("规格(mm)", ""))
            for col_idx, col_name in enumerate(cols):
                if "物料号" in col_name and pd.notna(row.iloc[col_idx]):
                    sap_code = str(row.iloc[col_idx]).split('.')[0].strip()
                    if not sap_code or sap_code.lower() == 'nan' or sap_code == '/': 
                        continue
                    weight = 0.0
                    if col_idx + 2 < len(cols): weight = row.iloc[col_idx + 2]
                    cleaned_rows.append({
                        "SAP号": sap_code, "产品名称": prod_name, "尺寸规格": spec, "物料描述": f"{prod_name} {spec}",
                        "Weight": weight if pd.notna(weight) and isinstance(weight, (int, float)) else 0.0,
                        "Pcs_Carton": 1, "L": 0.0, "W": 0.0, "H": 0.0, "CBM": 0.0
                    })
    else:
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
            l_val = float(row.get("L", 0)) if pd.notna(row.get("L", 0)) else 0.0
            w_val = float(row.get("W", 0)) if pd.notna(row.get("W", 0)) else 0.0
            h_val = float(row.get("H", 0)) if pd.notna(row.get("H", 0)) else 0.0
            cbm_val = float(row.get("CBM", 0)) if pd.notna(row.get("CBM", 0)) else 0.0
            if cbm_val == 0 and (l_val * w_val * h_val) > 0:
                cbm_val = (l_val * w_val * h_val) / 1e9 if l_val > 10 else l_val * w_val * h_val
            
            cleaned_rows.append({
                "SAP号": sap_code, "产品名称": row.get(name_col, ""), "尺寸规格": row.get(size_col, ""),
                "物料描述": row.get(desc_col, row.get(name_col, "")),
                "Weight": row.get(weight_col, 0.0), "Pcs_Carton": row.get(pcs_col, 1),
                "L": l_val, "W": w_val, "H": h_val, "CBM": round(cbm_val, 6)
            })
    return pd.DataFrame(cleaned_rows) if cleaned_rows else None


# --- 3. 初始化全局状态与高还原度模拟数据 ---
if 'product_dictionary' not in st.session_state:
    st.session_state.product_dictionary = pd.Dat
