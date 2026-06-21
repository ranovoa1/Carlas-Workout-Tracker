import streamlit as st
import pandas as pd
from datetime import datetime, timedelta


def show_export_tab(worksheet):
    """
    Displays the export tab with date filtering and export functionality.
    
    Args:
        worksheet: A Google Sheets worksheet object with get_all_records() method
    """
    st.header("Export Workout Log")
    
    # Create date picker columns
    col1, col2 = st.columns(2)
    
    with col1:
        from_date = st.date_input(
            "From",
            value=datetime.now() - timedelta(days=30),
            format="YYYY-MM-DD"
        )
    
    with col2:
        to_date = st.date_input(
            "To",
            value=datetime.now(),
            format="YYYY-MM-DD"
        )
    
    # Generate Export button
    if st.button("Generate Export", key="generate_export_btn"):
        # Read data from worksheet
        try:
            records = worksheet.get_all_records()
            
            if not records:
                st.warning("No data found in the worksheet.")
                return
            
            # Convert to DataFrame for easier filtering
            df = pd.DataFrame(records)
            
            # Convert Date column to datetime for filtering
            df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%d')
            
            # Filter by date range
            mask = (df['Date'] >= pd.Timestamp(from_date)) & (df['Date'] <= pd.Timestamp(to_date))
            filtered_df = df[mask].sort_values('Date')
            
            if filtered_df.empty:
                st.warning(f"No records found between {from_date} and {to_date}")
                return
            
            # Group by date and format as readable text
            export_text = format_export(filtered_df)
            
            # Show preview in text area
            st.code(export_text, language=None)
            
            # Download button
            st.download_button(
                label="Download as TXT",
                data=export_text,
                file_name=f"workout_log_{from_date}_{to_date}.txt",
                mime="text/plain"
            )
        
        except Exception as e:
            st.error(f"Error generating export: {str(e)}")


def format_export(df):
    """
    Formats the dataframe as clean, readable text grouped by date.
    
    Args:
        df: DataFrame with workout data
    
    Returns:
        Formatted string with grouped data
    """
    grouped = df.groupby('Date')
    
    output_lines = []
    output_lines.append("=" * 60)
    output_lines.append("WORKOUT LOG EXPORT")
    output_lines.append("=" * 60)
    output_lines.append("")
    
    for date, group in grouped:
        date_str = date.strftime("%A, %B %d, %Y")
        output_lines.append(f"\n{date_str}")
        output_lines.append("-" * 40)
        
        for _, row in group.iterrows():
            exercise = row['Exercise']
            sets = row['Sets']
            reps = row['Reps Done']
            weight = row['Weight (lbs)']
            notes = row['Notes']
            
            # Format exercise line
            output_lines.append(f"  {exercise}")
            output_lines.append(f"    Sets: {sets} | Reps: {reps} | Weight: {weight} lbs")
            
            if notes and str(notes).strip():
                output_lines.append(f"    Notes: {notes}")
            
            output_lines.append("")
    
    output_lines.append("=" * 60)
    
