# ConflictCompass — API 接口规范

所有接口 Base URL：`http://127.0.0.1:5000`

---

## 1. 话术生成

### POST /api/generate

**请求体：**
```json
{
  "lifecycle_stage": "离职与善后",
  "scenario": "裁员通知",
  "level": "中层管理",
  "emotion": "焦虑",
  "tone": "坚定但尊重",
  "extra_info": "该员工入职5年，表现一直不错但因业务线裁撤需协商解除"
}
```

**响应体：**
```json
{
  "success": true,
  "id": 1,
  "script": {
    "opening": "开场话术...",
    "core": "核心话术...",
    "closing": "收尾话术..."
  },
  "predictions": [
    {
      "question": "为什么是我？",
      "response": "这并非针对个人，而是公司业务调整的整体方案..."
    }
  ],
  "warnings": [
    {
      "type": "taboo",
      "word": "你必须",
      "position": "core",
      "suggestion": "建议使用：我们希望你能..."
    }
  ]
}
```

---

## 2. 话术优化

### POST /api/optimize

**请求体：**
```json
{
  "original_script": {
    "opening": "...",
    "core": "...",
    "closing": "..."
  },
  "direction": "更温和",
  "extra_notes": "加上关于补偿方案的说明"
}
```

**响应体：**
```json
{
  "success": true,
  "optimized_script": {
    "opening": "优化后开场...",
    "core": "优化后核心...",
    "closing": "优化后收尾..."
  },
  "changes_summary": "主要修改：1. 调整了开场语气...",
  "warnings": [...]
}
```

---

## 3. 合规检查

### POST /api/check

**请求体：**
```json
{
  "script": "要检查的话术全文"
}
```

**响应体：**
```json
{
  "success": true,
  "results": [
    {
      "category": "违法解除暗示",
      "status": "pass",
      "detail": ""
    },
    {
      "category": "威胁恐吓",
      "status": "violation",
      "detail": "原文包含威胁性表述...",
      "legal_reference": "《劳动合同法》第八十八条：以暴力、威胁或者非法限制人身自由的手段强迫劳动的...",
      "suggestion": "建议修改为..."
    }
  ],
  "summary": {
    "total": 9,
    "pass": 7,
    "warning": 1,
    "violation": 1
  },
  "taboo_words": [
    {
      "word": "你必须",
      "level": "escalation",
      "suggestion": "我们建议"
    }
  ]
}
```

---

## 4. 历史记录

### GET /api/history

**查询参数：**
- `lifecycle_stage`（可选）：按生命周期筛选
- `keyword`（可选）：按关键词搜索
- `limit`（可选，默认 20）
- `offset`（可选，默认 0）

**响应体：**
```json
{
  "success": true,
  "total": 50,
  "items": [
    {
      "id": 1,
      "lifecycle_stage": "离职与善后",
      "scenario": "裁员通知",
      "level": "中层管理",
      "emotion": "焦虑",
      "tone": "坚定但尊重",
      "preview": "开场话术前50字...",
      "created_at": "2026-06-12 14:30:00"
    }
  ]
}
```

### GET /api/history/<id>

获取单条历史详情（含完整话术和预判）

### DELETE /api/history/<id>

删除单条历史记录

---

## 5. 场景模板

### GET /api/templates

获取所有模板列表

### POST /api/templates

**请求体：**
```json
{
  "name": "自定义裁员模板",
  "lifecycle_stage": "离职与善后",
  "scenario": "裁员通知（温和版）",
  "default_tone": "温和关切",
  "default_notes": "适用于工龄5年以上老员工的裁员沟通"
}
```

### PUT /api/templates/<id>

编辑模板（请求体同上）

### DELETE /api/templates/<id>

删除模板（预置模板不可删除）

---

## 6. 健康检查

### GET /api/ping

返回服务状态和配置加载情况
