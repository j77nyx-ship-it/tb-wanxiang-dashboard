'''
# ====================== 🤖 AI投放一键诊断【暂时注释禁用】 ======================
st.markdown("---")
st.subheader("🤖 AI投放一键诊断")
st.info("💡该功能暂时禁用，可下载【待调整商品清单.csv】上传豆包网页版做AI分析。")
with st.expander("🔐 方舟API配置（仅浏览器会话保存，不会上传服务器）", expanded=False):
    api_key = st.text_input("Ark API‑Key", type="password", placeholder="火山方舟API Key")
    ep_id = st.text_input("推理接入点 Endpoint‑ID", placeholder="ep‑xxxxxxxxxx （模型接入点ID）")

run_ai = st.button("✨生成AI投放诊断报告", disabled=not (bool(api_key) and bool(ep_id)))

ai_report = ""
need_levels = ["🔻高花费低ROI", "🔴无成交", "⚠️观察待优化", "🟡零点击"]
if run_ai:
    with st.spinner("AI正在分析万相台投放数据，请稍候…"):
        try:
            import requests
            view_ai = df_prod_sum[df_prod_sum["等级"].isin(need_levels)].copy()
            csv_text_ai = view_ai[["商品ID","商品名称","总花费","总成交金额","整体ROI","等级","执行"]].to_csv(index=False)

            prompt = f"""
你是资深淘宝万相台投放优化专家，严格基于下面数据输出诊断报告。
【投放阈值】
保本目标ROI：{roi_target}
最小有效花费：{min_cost}元
CPC过高预警：{max_cpc_warn}元

【大盘汇总】
总花费：{tc:.2f}元
总GMV：{tg:.2f}元
整体ROI：{troi:.2f}
总点击：{int(tclk):,}

【待调整商品清单csv】
{csv_text_ai}

输出要求：
1. 大盘整体问题诊断；
2. TOP5优先处理商品（高花费低ROI、无成交优先）；
3. TOP5建议放大的优质商品；
4. 给出万相台后台可直接复制执行的操作清单；
5. 简短总结接下来2‑3天观察重点。
输出语言简洁，适合运营直接照着后台操作，不要冗余废话。
"""
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}
            payload = {
                "model": ep_id,
                "messages":[{"role":"user","content":prompt}],
                "temperature":0.4
            }
            resp = requests.post("https://ark.cn-beijing.volces.com/api/v3/chat/completions", headers=headers, json=payload, timeout=60)
            resp_json = resp.json()
            if resp.status_code == 200:
                ai_report = resp_json["choices"][0]["message"]["content"]
            else:
                ai_report = f"❌API调用失败：{resp_json}"
        except Exception as e:
            ai_report = f"❌异常：{str(e)}"

if ai_report:
    st.markdown("#### 📋AI投放诊断报告")
    st.markdown(ai_report)
    st.download_button("📥复制/下载AI报告", data=ai_report, file_name="AI万相台投放报告.txt", mime="text/plain")

# ====================== 🤖 AI投放一键诊断【结束】 ======================
'''
