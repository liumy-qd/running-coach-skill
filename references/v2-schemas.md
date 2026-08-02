# Running Coach V2 Schemas

## AthleteContext

结构化上下文的顶层字段：

```json
{
  "schema_version": "2.0",
  "as_of": "2026-08-01T08:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "request_type": "daily-check",
  "windows": {"health_days": 7, "activity_days": 14},
  "sources": [{"name": "coros", "retrieved_at": "...", "status": "ok"}],
  "coverage": {"level": "high", "score": 0.9, "present": [], "missing": [], "stale": [], "conflicts": []},
  "baselines": {"sleep": {}, "hrv": {}, "resting_hr": {}, "stress": {}, "training": {}},
  "current_state": {"recovery": {}, "subjective": {}, "environment": {}},
  "fitness": {},
  "goal": {},
  "training_history": {},
  "risk_flags": [],
  "evidence": []
}
```

每个重要结论都应能回指 `evidence` 中的来源、字段、日期窗口和数值。缺失数据不能写成否定事实。

## TrainingPrescription

```json
{
  "schema_version": "2.0",
  "decision": "as_planned|downshift|rest_or_recovery|ask",
  "readiness": "green|yellow|red",
  "confidence": 0.0,
  "evidence_window": {"start": "yyyy-MM-dd", "end": "yyyy-MM-dd"},
  "observations": [],
  "inferences": [],
  "session": {"type": "easy_run", "purpose": "...", "duration_min": 30, "distance_km": null, "intensity": "easy", "pace_low": null, "pace_high": null, "hr_low": null, "hr_high": null, "rpe_low": 2, "rpe_high": 4, "steps": []},
  "stop_rules": [],
  "downshift_option": "...",
  "missing_data": [],
  "feedback_questions": [],
  "next_checkpoint": "...",
  "evidence": []
}
```

安全不变量：`red` 不得为质量课；`yellow` 不得为间歇、阈值或长距离；医疗警讯必须包含停止和专业评估提示；任何处方都必须有停止规则和降级选项。
