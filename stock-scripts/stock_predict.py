#!/usr/bin/env python3
"""
A股次日涨跌预测模型
基于历史K线数据训练分类模型，预测次日涨跌幅
"""

import akshare as ak
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
import warnings
warnings.filterwarnings('ignore')

# ============ 1. 获取数据 ============
def get_stock_data(stock_code, start_date="20240101", end_date="20260317"):
    """获取股票历史K线数据"""
    try:
        df = ak.stock_zh_a_hist(
            symbol=stock_code, 
            period="daily", 
            start_date=start_date, 
            end_date=end_date, 
            adjust="qfq"
        )
        df = df.sort_values('日期')
        return df
    except Exception as e:
        print(f"获取数据失败: {e}")
        return None

# ============ 2. 特征工程 ============
def create_features(df):
    """创建技术指标特征"""
    df = df.copy()
    
    # 基础价格特征
    df['return'] = df['收盘'].pct_change()  # 日收益率
    df['high_low_ratio'] = (df['最高'] - df['最低']) / df['收盘']  # 振幅
    
    # 移动平均线
    for window in [5, 10, 20, 60]:
        df[f'ma{window}'] = df['收盘'].rolling(window=window).mean()
        df[f'ma{window}_ratio'] = df['收盘'] / df[f'ma{window}']
    
    # 成交量变化
    df['volume_change'] = df['成交量'].pct_change()
    df['volume_ma5'] = df['成交量'].rolling(5).mean()
    df['volume_ratio'] = df['成交量'] / df['volume_ma5']
    
    # RSI
    delta = df['收盘'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = df['收盘'].ewm(span=12, adjust=False).mean()
    ema26 = df['收盘'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # 布林带
    df['bb_mid'] = df['收盘'].rolling(20).mean()
    df['bb_std'] = df['收盘'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
    df['bb_position'] = (df['收盘'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    
    # 目标变量：次日涨跌（1=涨，0=跌）
    df['next_return'] = df['收盘'].shift(-1).pct_change()
    df['target'] = (df['next_return'] > 0).astype(int)
    
    return df

# ============ 3. 训练模型 ============
def train_model(df):
    """训练预测模型"""
    # 选择特征
    feature_cols = [
        'return', 'high_low_ratio',
        'ma5_ratio', 'ma10_ratio', 'ma20_ratio', 'ma60_ratio',
        'volume_change', 'volume_ratio',
        'rsi', 'macd_hist', 'bb_position'
    ]
    
    # 去除空值
    df_clean = df[feature_cols + ['target']].dropna()
    
    X = df_clean[feature_cols]
    y = df_clean['target']
    
    # 标准化
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # 划分训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42, shuffle=False
    )
    
    # 训练随机森林
    model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
    model.fit(X_train, y_train)
    
    # 评估
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"\n=== 模型评估 ===")
    print(f"测试集准确率: {accuracy:.2%}")
    print(f"\n分类报告:")
    print(classification_report(y_test, y_pred, target_names=['跌', '涨']))
    
    # 特征重要性
    print(f"\n特征重要性 (Top5):")
    importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    print(importance.head().to_string(index=False))
    
    return model, scaler, feature_cols

# ============ 4. 预测 ============
def predict_next(model, scaler, feature_cols, df):
    """预测次日涨跌"""
    # 获取最新数据
    latest = df.iloc[-1:][feature_cols].values
    latest_scaled = scaler.transform(latest)
    
    # 预测
    pred = model.predict(latest_scaled)[0]
    prob = model.predict_proba(latest_scaled)[0]
    
    # 获取次日涨跌幅预测
    latest_df = df.iloc[-1:]
    current_price = latest_df['收盘'].values[0]
    
    # 基于概率估算预期收益
    expected_return = prob[1] * 0.03 - prob[0] * 0.02  # 假设涨3%，跌2%
    
    print(f"\n=== 预测结果 ===")
    print(f"当前收盘价: {current_price:.2f}元")
    print(f"预测: {'上涨 📈' if pred == 1 else '下跌 📉'}")
    print(f"上涨概率: {prob[1]:.1%}")
    print(f"下跌概率: {prob[0]:.1%}")
    print(f"预期收益: {expected_return:.2%}")
    
    return pred, prob

# ============ 主程序 ============
if __name__ == "__main__":
    import sys
    
    stock_code = sys.argv[1] if len(sys.argv) > 1 else "300170"
    
    print(f"正在获取 {stock_code} 历史数据...")
    df = get_stock_data(stock_code)
    
    if df is None or len(df) < 60:
        print("数据获取失败或数据不足")
        exit(1)
    
    print(f"成功获取 {len(df)} 条K线数据")
    
    print("\n正在创建特征...")
    df_features = create_features(df)
    
    print("正在训练模型...")
    model, scaler, feature_cols = train_model(df_features)
    
    print("\n正在预测...")
    predict_next(model, scaler, feature_cols, df_features)
