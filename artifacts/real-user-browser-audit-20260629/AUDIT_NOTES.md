# Real User Browser Audit

Browser: system Edge (headed)
Frontend: http://127.0.0.1:5174
Backend API routed to: http://127.0.0.1:54321

## Steps
1. 打开项目列表
   - Screenshot: 01-project-list.png
   - Bytes: 155062
2. 进入三个和尚项目
   - Screenshot: 02-project-entry.png
   - Bytes: 181114
3. 打开分镜模块
   - Screenshot: 03-storyboard-module.png
   - Bytes: 115753
4. 选择镜头并查看右侧工作台
   - Screenshot: 04-shot-workbench.png
   - Bytes: 183807
5. 展开结构化/提示词/验收面板
   - Screenshot: 05-shot-panels-open.png
   - Bytes: 189737
6. 进入视觉资产模块
   - Screenshot: 06-visual-assets.png
   - Bytes: 92304
7. 尝试进入导出模块
   - Screenshot: 07-export-attempt.png
   - Bytes: 138220

## Findings Data

```json
{
  "found": {
    "分镜生产": true,
    "创作沙盘": true,
    "视觉资产": true,
    "结构化镜头": false,
    "角色站位": false,
    "动作节拍": false,
    "提示词编译器": false,
    "重新编译": false,
    "生成首帧": false,
    "生成视频": false,
    "验收反馈": false,
    "导出": true,
    "交付历史": true,
    "JSON": true,
    "当前选中镜头": false,
    "上一镜": false,
    "下一镜": false
  },
  "exportButtonState": {
    "disabled": false,
    "text": "📥导出",
    "className": "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all text-[14px] text-slate-400 hover:bg-slate-800/50"
  },
  "buttons": [
    {
      "text": "分镜生产",
      "disabled": false
    },
    {
      "text": "🎬\n分镜生产",
      "disabled": false
    },
    {
      "text": "🎨\n视觉资产",
      "disabled": false
    },
    {
      "text": "📥\n导出",
      "disabled": false
    },
    {
      "text": "打开分镜模块",
      "disabled": false
    },
    {
      "text": "登记交付",
      "disabled": false
    },
    {
      "text": "导出 JSON 并登记",
      "disabled": false
    },
    {
      "text": "复制交付摘要",
      "disabled": false
    },
    {
      "text": "复制交付摘要",
      "disabled": false
    },
    {
      "text": "回到分镜处理阻塞项",
      "disabled": false
    },
    {
      "text": "📄 导出 PDF",
      "disabled": true
    },
    {
      "text": "📄 导出 Word",
      "disabled": true
    },
    {
      "text": "📄 导出 JSON",
      "disabled": false
    },
    {
      "text": "📄 导出 Final Draft",
      "disabled": true
    }
  ],
  "recordCount": 2,
  "consoleIssues": [
    {
      "type": "requestfailed",
      "text": "http://127.0.0.1:54321/api/books :: net::ERR_ABORTED"
    },
    {
      "type": "requestfailed",
      "text": "http://127.0.0.1:54321/api/nodes/registry :: net::ERR_ABORTED"
    },
    {
      "type": "requestfailed",
      "text": "http://127.0.0.1:54321/api/books :: net::ERR_ABORTED"
    }
  ]
}
```
