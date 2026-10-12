Trained global models live here as `<domain>-<timeframe>s.txt` (LightGBM) with a
`.json` metadata file and a `.report.json` evaluation report. `tartar watch`
loads the one matching the data source (`trades` for pump.fun trade streams,
`ohlcv` for candle-only sources) and timeframe. Create them with
`tartar record` + `tartar train`, or let `tartar learn` do both continuously.
