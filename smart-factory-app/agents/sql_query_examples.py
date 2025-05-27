# smart-factory-app/agents/sql_query_examples.py

SQL_QUERY_EXAMPLES = [
    {
        "id": "daily_summary_report",
        "name": "Daily Summary Report Query",
        "description": "Calculates daily production metrics like part count, uptime, downtime, and (implicitly by providing components) OEE, Utilization, Productivity, Quality for a given equipment and shift.",
        "natural_language_equivalent": "Can you provide the daily summary report for equipment :equipment_id from :start_date to :end_date for shift :shift_id?",
        "query_template": """
WITH ShiftTimes AS (
    SELECT
        s.shift_id,
        s.shift_name,
        make_timestamptz(dd.year_val, dd.month_val, dd.day_val, smd.start_hour, smd.start_minute, 0, dd.time_zone) AS shift_start_time,
        make_timestamptz(dd.year_val, dd.month_val, dd.day_val, smd.end_hour, smd.end_minute, 0, dd.time_zone) AS shift_end_time
    FROM shift s
    JOIN d_date dd ON s.date_id = dd.date_id
    JOIN shift_meta_data smd ON s.shift_meta_id = smd.shift_meta_id
    WHERE s.shift_id = :shift_id AND dd.full_date BETWEEN :start_date AND :end_date
),
EquipmentDataAgg AS (
    SELECT
        equipment_id,
        SUM(part_count) AS total_part_count,
        SUM(CASE WHEN status = 'running' THEN duration_minutes ELSE 0 END) AS total_uptime_minutes,
        SUM(CASE WHEN status = 'down' THEN duration_minutes ELSE 0 END) AS total_downtime_minutes,
        SUM(duration_minutes) AS total_duration_minutes
    FROM equipment_data_daily edd -- Assuming this table has daily aggregated data with status and duration
    JOIN ShiftTimes st ON edd.date >= date(st.shift_start_time) AND edd.date <= date(st.shift_end_time) -- Simplified join
    WHERE edd.equipment_id = :equipment_id
      AND edd.date BETWEEN :start_date AND :end_date
    GROUP BY equipment_id
),
BreakTimes AS (
    SELECT
        sb.shift_id,
        SUM(sb.break_duration_minutes) AS total_break_minutes
    FROM shift_break sb
    WHERE sb.shift_id = :shift_id
    GROUP BY sb.shift_id
)
SELECT
    st.shift_name,
    st.shift_start_time,
    st.shift_end_time,
    eda.equipment_id,
    eda.total_part_count,
    eda.total_uptime_minutes,
    eda.total_downtime_minutes,
    (EXTRACT(EPOCH FROM (st.shift_end_time - st.shift_start_time)) / 60) AS total_shift_duration_minutes,
    COALESCE(bt.total_break_minutes, 0) AS total_break_minutes,
    ( (EXTRACT(EPOCH FROM (st.shift_end_time - st.shift_start_time)) / 60) - COALESCE(bt.total_break_minutes, 0) ) AS planned_production_time_minutes
FROM ShiftTimes st
LEFT JOIN EquipmentDataAgg eda ON TRUE -- Assuming one equipment_id is passed, or eda needs equipment_id in GROUP BY
LEFT JOIN BreakTimes bt ON st.shift_id = bt.shift_id;
""",
        "parameters": ["equipment_id", "start_date", "end_date", "shift_id"],
        "expected_intent": "get_daily_summary",
        "keywords": ["daily summary", "part count", "uptime", "downtime", "shift report", "oee components", "utilization components", "productivity components", "quality components"],
        "tables_involved": ["equipment_data_daily", "shift", "shift_break", "d_date", "shift_meta_data"]
    },
    {
        "id": "machine_goal_capacity",
        "name": "Machine Goal/Capacity Query",
        "description": "Fetches the production goals (part count, uptime) for equipment based on hourly or daily aggregation. The '{table_name}' parameter determines the aggregation level (e.g., 'equipment_data_hourly' or 'equipment_data_daily').",
        "natural_language_equivalent": "What is the production goal or capacity for machine :equipment_id between :start_date and :end_date for shift :shift_id, product :product_id, facility :facility_id, using the {table_name} aggregation table?",
        "query_template": """
SELECT 
    e.machine_name,
    ed.timestamp AS period_start, -- Assuming 'timestamp' for hourly, 'date' for daily
    ed.target_part_count, -- Placeholder: actual column name for target part count
    ed.target_uptime_percentage -- Placeholder: actual column name for target uptime
FROM 
    equipment e
JOIN 
    {table_name} ed ON e.machine_id = ed.machine_id -- {table_name} is dynamic, e.g., equipment_data_hourly
WHERE 
    e.equipment_id = :equipment_id
    AND ed.product_id = :product_id -- Assuming goals are per product
    AND ed.facility_id = :facility_id -- Assuming goals are per facility
    AND ed.timestamp BETWEEN :start_date AND :end_date -- Adjust column name if using daily
    AND ed.shift_id = :shift_id -- If applicable for the aggregation level
ORDER BY 
    period_start DESC;
""",
        "parameters": ["equipment_id", "start_date", "end_date", "shift_id", "product_id", "facility_id", "table_name"],
        "expected_intent": "get_machine_goal",
        "keywords": ["goal", "capacity", "target", "part count goal", "uptime goal", "production target"],
        "tables_involved": ["equipment_data_hourly", "equipment_data_daily", "equipment"] # Actual table depends on {table_name}
    },
    {
        "id": "oee_production_components",
        "name": "OEE & Production Components Query",
        "description": "Calculates total part count and uptime for a machine from an aggregated table. These are components for OEE and Production Rate. The '{AGGREGATED_TABLE_NAME}' parameter specifies the source table (e.g., 'equipment_data_hourly', 'equipment_data_daily') and '{time_column}' specifies the relevant time column in that table.",
        "natural_language_equivalent": "Calculate part count and uptime for machine :equipment_id from :start_date to :end_date for shift :shift_id, using table {AGGREGATED_TABLE_NAME} and time column {time_column}.",
        "query_template": """
SELECT 
    SUM(COALESCE(edd.total_production, edd.part_count, 0)) as total_part_count, -- Adapt based on actual column names in daily/hourly
    SUM(COALESCE(edd.total_uptime_minutes, edd.uptime_duration, 0)) as total_uptime_minutes -- Adapt based on actual column names
FROM 
    {AGGREGATED_TABLE_NAME} edd -- This will be replaced by equipment_data_hourly or equipment_data_daily
WHERE 
    edd.equipment_id = :equipment_id
    AND edd.{time_column} BETWEEN :start_date AND :end_date -- {time_column} needs to be 'timestamp' or 'date'
    AND edd.shift_id = :shift_id; -- Assuming shift_id is present
""",
        "parameters": ["equipment_id", "start_date", "end_date", "shift_id", "AGGREGATED_TABLE_NAME", "time_column"],
        "expected_intent": "calculate_oee_components",
        "keywords": ["part count", "uptime", "OEE components", "production components"],
        "tables_involved": ["equipment_data_hourly", "equipment_data_daily"] # Actual table depends on {AGGREGATED_TABLE_NAME}
    },
    {
        "id": "machine_speed",
        "name": "Machine Speed Query",
        "description": "Fetches the most recent machine speed (parts per hour) for a given equipment, considering shift times. Requires current time in the target timezone.",
        "natural_language_equivalent": "What is the current machine speed for :equipment_id as of :zoned_current_time, considering data since :start_date?",
        "query_template": """
WITH ShiftData AS (
    SELECT 
        s.shift_id,
        dd.full_date,
        smd.start_hour, 
        smd.start_minute,
        smd.end_hour, 
        smd.end_minute,
        dd.time_zone
    FROM shift s
    JOIN d_date dd ON s.date_id = dd.date_id
    JOIN shift_meta_data smd ON s.shift_meta_id = smd.shift_meta_id
    WHERE dd.full_date = :start_date -- Assuming start_date is the specific date of interest
),
CurrentShiftActive AS (
    SELECT 
        sd.shift_id,
        make_timestamptz(EXTRACT(YEAR FROM sd.full_date)::integer, EXTRACT(MONTH FROM sd.full_date)::integer, EXTRACT(DAY FROM sd.full_date)::integer, sd.start_hour, sd.start_minute, 0, sd.time_zone) AS shift_start_zoned,
        make_timestamptz(EXTRACT(YEAR FROM sd.full_date)::integer, EXTRACT(MONTH FROM sd.full_date)::integer, EXTRACT(DAY FROM sd.full_date)::integer, sd.end_hour, sd.end_minute, 0, sd.time_zone) AS shift_end_zoned
    FROM ShiftData sd
    WHERE :zoned_current_time BETWEEN 
        make_timestamptz(EXTRACT(YEAR FROM sd.full_date)::integer, EXTRACT(MONTH FROM sd.full_date)::integer, EXTRACT(DAY FROM sd.full_date)::integer, sd.start_hour, sd.start_minute, 0, sd.time_zone) AND
        make_timestamptz(EXTRACT(YEAR FROM sd.full_date)::integer, EXTRACT(MONTH FROM sd.full_date)::integer, EXTRACT(DAY FROM sd.full_date)::integer, sd.end_hour, sd.end_minute, 0, sd.time_zone)
    LIMIT 1
),
EquipmentDataShiftAgg AS (
    SELECT 
        eds.equipment_id,
        SUM(eds.part_count) AS total_parts,
        SUM(EXTRACT(EPOCH FROM (eds.end_time - eds.start_time))) / 3600.0 AS total_hours  -- Duration in hours
    FROM equipment_data_shift eds -- Assuming this table has part_count per shift interval for equipment
    JOIN CurrentShiftActive csa ON eds.shift_id = csa.shift_id -- Only data from the current active shift
    WHERE eds.equipment_id = :equipment_id
      AND eds.start_time >= csa.shift_start_zoned 
      AND eds.end_time <= csa.shift_end_zoned
    GROUP BY eds.equipment_id
    HAVING SUM(EXTRACT(EPOCH FROM (eds.end_time - eds.start_time))) > 0 -- Avoid division by zero
)
SELECT 
    COALESCE(edsa.total_parts / edsa.total_hours, 0) AS parts_per_hour
FROM EquipmentDataShiftAgg edsa;
""",
        "parameters": ["equipment_id", "start_date", "zoned_current_time"],
        "expected_intent": "get_machine_speed",
        "keywords": ["machine speed", "speed", "parts per hour", "rate"],
        "tables_involved": ["equipment_data_shift", "d_date", "shift", "shift_meta_data"] # Assuming equipment_data_metric and equipment_data are part of equipment_data_shift logic or pre-aggregation.
    },
    {
        "id": "machine_last_running_status",
        "name": "Machine Last Running Status Query",
        "description": "Determines and returns the last known running status of a machine, including how long it has been in that state. Requires the current date and time.",
        "natural_language_equivalent": "What is the last running status for machine :equipment_id as of :current_date_time?",
        "query_template": """
WITH LastStatus AS (
    SELECT 
        es.equipment_id,
        es.status_code_id, -- Assuming equipment_status has a foreign key to equipment_status_code
        esc.status_name,   -- Fetched from equipment_status_code table
        es.start_time,
        es.end_time,
        COALESCE(es.end_time, :current_date_time) - es.start_time AS duration_in_state,
        ROW_NUMBER() OVER (PARTITION BY es.equipment_id ORDER BY es.start_time DESC) as rn
    FROM equipment_status es
    JOIN equipment_status_code esc ON es.status_code_id = esc.status_code_id -- Join to get status name
    WHERE es.equipment_id = :equipment_id AND es.start_time <= :current_date_time 
),
LastAlarm AS (
    SELECT
        ea.equipment_id,
        ea.alarm_description,
        ea.start_timestamp AS alarm_start_time,
        ROW_NUMBER() OVER (PARTITION BY ea.equipment_id ORDER BY ea.start_timestamp DESC) as rn_alarm
    FROM equipment_alarm ea
    WHERE ea.equipment_id = :equipment_id AND ea.start_timestamp <= :current_date_time
      AND ea.end_timestamp IS NULL -- Consider active alarms or very recent ones
)
SELECT 
    ls.equipment_id,
    ls.status_name AS last_status,
    ls.start_time AS status_start_time,
    EXTRACT(EPOCH FROM ls.duration_in_state) / 60.0 AS duration_in_current_status_minutes, -- Duration in minutes
    la.alarm_description AS last_active_alarm_description,
    la.alarm_start_time AS last_active_alarm_start_time
FROM LastStatus ls
LEFT JOIN LastAlarm la ON ls.equipment_id = la.equipment_id AND la.rn_alarm = 1
WHERE ls.rn = 1;
""",
        "parameters": ["equipment_id", "current_date_time"],
        "expected_intent": "get_last_running_status",
        "keywords": ["status", "running status", "machine state", "last status", "current status", "alarm"],
        "tables_involved": ["equipment_alarm", "equipment_status", "equipment_status_code"] # Removed shift, d_date, app_metadata unless directly used by status logic
    }
]

if __name__ == "__main__":
    # Helper to print out the examples for verification
    import json
    print(f"Found {len(SQL_QUERY_EXAMPLES)} SQL query examples.")
    for i, example in enumerate(SQL_QUERY_EXAMPLES):
        print(f"\n--- Example {i+1}: {example['id']} ---")
        print(f"  Name: {example['name']}")
        print(f"  Description: {example['description']}")
        print(f"  Expected Intent: {example['expected_intent']}")
        print(f"  Keywords: {example['keywords']}")
        print(f"  Tables Involved: {example['tables_involved']}")
        print(f"  Parameters: {example['parameters']}")
        print(f"  Query Template:\n{example['query_template'][:300]}...") # Print snippet
        # Verify all parameters are in template (simple check)
        for param in example['parameters']:
            if f":{param}" not in example['query_template'] and "{"+param+"}" not in example['query_template']: # Check for :param and {param}
                 print(f"  WARNING: Parameter ':{param}' or '{{{param}}}' not found in query_template for example '{example['id']}'.")
