# ESP32 Weather Dashboard Troubleshooting

## Quick Fix Summary

The main issue was that Streamlit wasn't configured to accept external connections in the Docker container. Here are the fixes applied:

### 1. Fixed Streamlit Server Binding
**Problem**: Streamlit only bound to localhost inside the container.
**Solution**: Added `--server.address=0.0.0.0` to the Streamlit command.

### 2. Added Health Checks
**Problem**: Silent failures when database or serial port aren't available.
**Solution**: Added `health_check.py` to verify connectivity before starting Streamlit.

### 3. Made Serial Port Optional
**Problem**: App would crash if serial device isn't available.
**Solution**: Made serial worker gracefully handle missing devices.

### 4. Enhanced Error Handling
**Problem**: Poor error messages when things go wrong.
**Solution**: Added try/catch blocks and informative error messages.

## How to Run

1. Make sure your PostgreSQL database is running and accessible
2. Run: `chmod +x run.sh && ./run.sh`
3. Open http://localhost:8501 in your browser

## Common Issues

### Streamlit Won't Connect
- **Symptom**: Container runs but browser can't connect to http://localhost:8501
- **Cause**: Missing `--server.address=0.0.0.0` parameter
- **Status**: ✅ FIXED

### Database Connection Errors
- **Symptom**: "Database connection failed" message in Streamlit
- **Cause**: PostgreSQL not running or incorrect credentials
- **Check**: Run `python health_check.py` to test database connectivity

### Serial Port Issues
- **Symptom**: No data appearing in dashboard
- **Cause**: Serial device not available or permissions issue
- **Solution**: App will continue without serial data (check logs)

### Table Not Found
- **Symptom**: SQL error about missing table
- **Cause**: Database table `weatherDataFromSite1` doesn't exist
- **Solution**: Create the table in your PostgreSQL database

## Environment Variables (Optional)

You can override database settings with environment variables:
```bash
export DB_HOST=your_host
export DB_NAME=your_database
export DB_USER=your_username
export DB_PASSWORD=your_password
export DB_PORT=5432
```

## Testing

Run the health check independently:
```bash
python health_check.py
```

This will test:
- ✅ Database connectivity
- ⚠️ Serial port availability (optional)
- ✅ Required table existence
