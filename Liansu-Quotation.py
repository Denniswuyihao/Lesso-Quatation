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
        # 针对标准的管材/管件模板 (如 1000088430.jpg)
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
                # 如果数值大于10，说明是用毫米(mm)写的，除以1e9；如果是小于10的浮点数，说明已经是米(M)了
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
            
    return pd.DataFrame(cleaned_rows) if cleaned_rows else st.warning("未能从表格中解析出有效行，请检查表头。")


# --- 3. 初始化全局状态与高还原度模拟数据 ---
if 'product_dictionary' not in st.session_state:
    # 默认初始化数据完全还原您给的截图中的真实经典SKU
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
    st.se
