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
            cbm_val = float(ro
