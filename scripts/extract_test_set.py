import pandas as pd


def extract_test_set_from_file(file_path, output_excel_path, sample_size=50):
    # 1. 核心修改：使用 read_json 读取 JSON 数组格式
    try:
        # 注意：如果文件很大，read_json 会占用较多内存
        df_all = pd.read_json(file_path, encoding="utf-8")
    except Exception as e:
        print(f"❌ 读取失败，请检查文件格式是否为标准 JSON 数组: {e}")
        return

    print(f"总数据量: {len(df_all)} 条")

    # 2. 随机抽样
    # frac=1 表示打乱所有数据，n 表示抽取固定数量
    if len(df_all) > sample_size:
        df_sampled = df_all.sample(n=sample_size, random_state=42)
    else:
        df_sampled = df_all.copy()

    # 3. 构造人工标注所需的列
    # 我们保留原始字段，并新增以 'GT_' (Ground Truth) 开头的待填列

    # 定义你论文表 6-7 需要的标注维度
    gt_columns = {
        "GT_标题评分(1-5)": "",
        "GT_描述评分(1-5)": "",
        "GT_严重程度(手动填)": "",
        "GT_受影响版本(手动填)": "",
        "GT_复现步骤评分(1-5)": "",
    }

    # 批量添加空列
    for col, value in gt_columns.items():
        df_sampled[col] = value

    # 4. 调整列顺序，方便人工阅读
    # 建议顺序：ID -> 原始标题 -> 原始描述 -> [标注列...] -> 系统提取结果 -> URL
    # 请根据你 CSV 实际的列名修改下面的字符串（如 'title', 'description'）
    existing_cols = df_sampled.columns.tolist()

    display_order = [
        "title",
        "GT_标题评分(1-5)",
        "description",
        "GT_描述评分(1-5)",
        "steps_to_reproduce",
        "GT_复现步骤评分(1-5)",
        "severity",
        "GT_严重程度(手动填)",
        "version",
        "GT_受影响版本(手动填)",
        "url",
    ]

    # 只保留存在的列，防止报错
    final_cols = [c for c in display_order if c in df_sampled.columns]
    df_final = df_sampled[final_cols]

    # 5. 导出为高度可读的 Excel
    with pd.ExcelWriter(output_excel_path, engine="xlsxwriter") as writer:
        df_final.to_excel(writer, index=False, sheet_name="Evaluation")

        workbook = writer.book
        worksheet = writer.sheets["Evaluation"]

        # 设置格式：左对齐、自动换行、垂直居上
        format_wrap = workbook.add_format(
            {"text_wrap": True, "valign": "top", "align": "left"}
        )

        # 美化：给长文本列设置宽度
        worksheet.set_column("B:B", 30, format_wrap)  # Title 列
        worksheet.set_column("C:C", 50, format_wrap)  # Description 列
        worksheet.set_column("D:H", 15)  # 标注区域加宽方便填写

    print(f"✅ 成功抽取 {len(df_final)} 条数据，已生成标注表格: {output_excel_path}")


if __name__ == "__main__":
    file_path = r"D:\STUDY\毕设\Code\defect-collector\scripts\all.csv"
    extract_test_set_from_file(file_path, "实验标注表.xlsx", 300)
