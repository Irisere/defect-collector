import os
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import rcParams

# 设置中文字体，防止图片中的中文乱码 (根据你的系统调整，Windows通常是SimHei, macOS是Arial Unicode MS)
rcParams["font.family"] = "SimHei"
# 解决负号显示问题
rcParams["axes.unicode_minus"] = False


# 1. 时延分析：从日志文件提取耗时
def analyze_latency_with_plot(log_file_path, output_dir="paper_figures"):
    latencies = []
    # 匹配日志中的耗时信息
    pattern = re.compile(r"共耗时: ([\d.]+) 秒")

    # 1. 读取数据
    if not os.path.exists(log_file_path):
        print(f"错误: 文件不存在 {log_file_path}")
        return

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                latencies.append(float(match.group(1)))

    if not latencies:
        print("未发现耗时数据")
        return

    # --- 核心修改：取最近（末尾）的 1000 条 ---
    # 如果总数少于 1000，则取全量
    if len(latencies) > 1000:
        latencies = latencies[-1000:]
        print(f"提示：已从原始数据中截取最近的 1000 条进行分析")

    # 2. 计算统计量 (基于截取后的 1000 条数据)
    all_latencies = np.array(latencies)
    n = len(all_latencies)
    mean = np.mean(all_latencies)
    std_dev = np.std(all_latencies, ddof=1)

    # 计算 95% 置信区间 (Z=1.96)
    z_score = 1.96
    margin_error = z_score * (std_dev / np.sqrt(n))
    ci_lower = mean - margin_error
    ci_upper = mean + margin_error

    # 3. 终端打印结果
    print(f"\n--- 1. 结构化处理时延分析 (n={n}) ---")
    print(f"样本均值 (x̄): {mean:.2f}s")
    print(f"标准差 (s): {std_dev:.2f}s")
    print(f"95% 置信区间: [{ci_lower:.2f}s, {ci_upper:.2f}s]")

    # 4. 绘图数据预处理：为了防止长尾拉长X轴，使用第95百分位数截断绘图
    p_high = np.percentile(all_latencies, 98)
    plot_data = all_latencies[all_latencies <= p_high]

    # 5. 生成毕设可用图片
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    sns.set_theme(style="whitegrid", font="SimHei")
    plt.figure(figsize=(9, 5))

    # 绘制直方图和KDE
    ax = sns.histplot(
        plot_data,
        kde=True,
        bins=50,
        color="#5B9BD5",
        edgecolor="white",
        alpha=0.8,
        line_kws={"linewidth": 2.5},
    )

    # 绘制均值线和置信区间阴影
    plt.axvline(
        mean, color="#ED7D31", linestyle="--", linewidth=2, label=f"均值: {mean:.2f}s"
    )
    plt.axvspan(ci_lower, ci_upper, color="#ED7D31", alpha=0.2, label="95% 置信区间")

    plt.xlim(0, max(plot_data) * 1.05)

    plt.title(f"缺陷报告结构化处理时延分布图 (n={n})", fontsize=15, pad=15)
    plt.xlabel("处理时延 (单位: 秒)", fontsize=12)
    plt.ylabel("样本频数", fontsize=12)
    plt.legend(fontsize=11, loc="upper right")

    plt.tight_layout()

    fig_path_pdf = os.path.join(output_dir, "latency_distribution.pdf")
    fig_path_png = os.path.join(output_dir, "latency_distribution.png")
    plt.savefig(fig_path_pdf, dpi=300)
    plt.savefig(fig_path_png, dpi=300)

    print(f"分析图片已保存至: {output_dir}")
    plt.close()

    return mean, ci_lower, ci_upper


# 2. 提取准确率分析 (对比 LLM 结果与人工标注)


def plot_accuracy_results(stats_result, output_dir="paper_figures"):
    """生成 P/R/F1 柱状图和质量评分横向条形图的组合图"""

    # 1. 准备分类字段数据 (severity, version)
    cls_fields = ["severity", "version"]
    categories = ["精准率 (P)", "召回率 (R)", "F1-Score"]

    # 提取数值 (去掉百分号)
    cls_data = []
    for f in cls_fields:
        res = stats_result.get(f, {})
        # 增加容错，如果字段不存在则默认为 0
        p = float(res.get("P", "0%").strip("%")) if "P" in res else 0
        r = float(res.get("R", "0%").strip("%")) if "R" in res else 0
        f1 = float(res.get("F1", "0%").strip("%")) if "F1" in res else 0
        cls_data.append([p, r, f1])

    # 2. 准备评分字段数据 (title, description, steps)
    # 映射更专业的展示名称
    score_map = {
        "title": "标题生成质量",
        "description": "缺陷描述质量",
        "steps_to_reproduce": "复现步骤质量",
    }
    score_labels = []
    score_values = []
    for f, label in score_map.items():
        val = float(stats_result.get(f, {}).get("Avg_Score", 0))
        score_labels.append(label)
        score_values.append(val)

    # 防止无数据时绘图报错
    if not cls_data and not score_values:
        print("⚠ 无有效指标数据，跳过绘图")
        return

    # 统一设置绘图风格
    sns.set_theme(style="whitegrid", font="SimHei")

    # 开始绘图 (1行2列组合图)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # --- 左图：分类字段 P/R/F1 对比柱状图 ---
    x = np.arange(len(categories))
    width = 0.35
    ax1.bar(
        x - width / 2,
        cls_data[0],
        width,
        label="严重程度 (Severity)",
        color="#5B9BD5",  # 经典蓝
        edgecolor="white",
    )
    if len(cls_data) > 1:  # 确保 version 数据存在
        ax1.bar(
            x + width / 2,
            cls_data[1],
            width,
            label="受影响版本 (Version)",
            color="#ED7D31",  # 商务橙
            edgecolor="white",
        )
    ax1.set_ylabel("百分比 (%)", fontsize=12)
    ax1.set_title("表 6-7 核心分类字段提取性能对比", fontsize=14, pad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, fontsize=11)
    ax1.set_ylim(0, 110)  # 留出标注空间
    ax1.legend(fontsize=10, loc="lower right")

    # 在柱状图上标注数值
    for i in range(len(cls_data)):
        for j, v in enumerate(cls_data[i]):
            offset = -width / 2 if i == 0 else width / 2
            ax1.text(
                j + offset,
                v + 1,
                f"{v:.1f}%",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

    # --- 右图：长文本评分横向条形图 ---
    # 使用渐变色体现质量
    colors = sns.color_palette("viridis_r", len(score_labels))
    y_pos = np.arange(len(score_labels))
    ax2.barh(y_pos, score_values, color=colors, height=0.6, edgecolor="white")
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(score_labels, fontsize=11)
    ax2.set_xlabel("量化得分 (百分制)", fontsize=12)
    ax2.set_title("表 6-7 长文本结构化提取质量评分", fontsize=14, pad=10)
    ax2.set_xlim(0, 110)

    # 在条形图右侧标注数值
    for i, v in enumerate(score_values):
        ax2.text(
            v + 1,
            i,
            f"{v:.1f}",
            va="center",
            ha="left",
            fontweight="bold",
            color=colors[i],
        )

    plt.tight_layout()

    # 保存
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    fig_path = os.path.join(output_dir, "accuracy_analysis.png")
    plt.savefig(fig_path, dpi=300)
    print(f"📈 准确率分析统计图表已保存至: {output_dir}")
    plt.close()


def analyze_accuracy_from_excel(excel_path, output_dir="paper_figures"):
    # 1. 读取人工标注完成后的 Excel 文件
    # 确保你已经安装了 openpyxl: pip install openpyxl
    df = pd.read_excel(excel_path)

    # 2. 定义评估维度映射关系
    # 格式：字段名: (系统结果列名, 人工标注列名, 评价模式)
    field_map = {
        "severity": ("severity", "GT_严重程度(手动填)", "classification"),
        "version": ("version", "GT_受影响版本(手动填)", "classification"),
        "title": (None, "GT_标题评分(1-5)", "score"),  # 标题只有评分
        "description": (None, "GT_描述评分(1-5)", "score"),  # 描述只有评分
        "steps_to_reproduce": (None, "GT_复现步骤评分(1-5)", "score"),  # 步骤只有评分
    }

    stats_result = {}

    for field, (sys_col, gt_col, mode) in field_map.items():
        if mode == "classification":
            # 分类字段计算 P, R, F1
            tp, fp, fn = 0, 0, 0

            for _, row in df.iterrows():
                # 获取系统值和人工值，处理空值并转为字符串
                pred = (
                    str(row.get(sys_col, "")).strip().lower()
                    if pd.notna(row.get(sys_col))
                    else ""
                )
                gt = (
                    str(row.get(gt_col, "")).strip().lower()
                    if pd.notna(row.get(gt_col))
                    else ""
                )

                if gt == "" and pred == "":
                    continue  # 两者皆空不计入统计

                if pred == gt and pred != "":
                    tp += 1
                elif pred != gt and pred != "":
                    fp += 1  # 预测错了
                elif pred == "" and gt != "":
                    fn += 1  # 漏报了

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = (
                2 * (precision * recall) / (precision + recall)
                if (precision + recall) > 0
                else 0
            )

            stats_result[field] = {
                "P": f"{precision:.2%}",
                "R": f"{recall:.2%}",
                "F1": f"{f1:.2%}",
            }

        elif mode == "score":
            # 评分字段计算百分制均值
            scores = []
            for _, row in df.iterrows():
                val = row.get(gt_col)
                if pd.notna(val) and isinstance(val, (int, float)):
                    # 将 1-5 分转化为百分制
                    scores.append((val / 5) * 100)

            avg_score = np.mean(scores) if scores else 0
            stats_result[field] = {"Avg_Score": f"{avg_score:.2f}"}

    # 3. 打印分析报告
    print("\n" + "=" * 50)
    print("智能化提取准确率实验分析报告")
    print("=" * 50)
    for f, v in stats_result.items():
        print(f"【{f:18}】: {v}")
    # print("=" * 50)
    # plot_accuracy_results(stats_result, output_dir)


if __name__ == "__main__":
    FIG_DIR = "paper_figures"
    # # 1. 解析你的 extractor.log
    # log_path = r"D:\STUDY\毕设\Code\defect-collector\collect_api.log"
    # analyze_latency_with_plot(log_path, FIG_DIR)

    # 2. 手工标注的对比文件 (用于论文实验)
    excel_completed_path = (
        r"D:\STUDY\毕设\Code\defect-collector\scripts\实验标注表.xlsx"
    )
    print("\n>>> 开始运行智能化提取准确率分析...")
    analyze_accuracy_from_excel(excel_completed_path, FIG_DIR)
