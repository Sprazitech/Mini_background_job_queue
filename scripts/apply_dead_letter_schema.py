#!/usr/bin/env python
"""
Dead letter queue schema setup script.
This script applies the dead letter queue schema extensions to the database.
"""

import os
import asyncio
import asyncpg
from pathlib import Path


async def apply_dead_letter_schema(database_url: str):
    """Apply dead letter queue schema extensions."""
    
    # Read the dead letter queue SQL file
    schema_path = Path(__file__).parent / "dead_letter_queue.sql"
    if not schema_path.exists():
        print(f"Dead letter queue schema file not found: {schema_path}")
        return False
    
    try:
        # Parse the connection URL
        if database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        
        print(f"Connecting to database for dead letter queue setup...")
        conn = await asyncpg.connect(database_url)
        
        # Read and execute the schema
        sql = schema_path.read_text()
        print(f"Applying dead letter queue schema from {schema_path}...")
        
        # Split into individual statements
        statements = sql.split(';')
        for i, statement in enumerate(statements):
            statement = statement.strip()
            if statement:
                try:
                    await conn.execute(statement)
                    print(f"✓ Executed dead letter queue statement {i + 1}")
                except Exception as e:
                    print(f"✗ Error in statement {i + 1}: {e}")
        
        await conn.close()
        print("✓ Dead letter queue schema applied successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Error applying dead letter queue schema: {e}")
        return False


async def verify_dead_letter_schema(database_url: str):
    """Verify dead letter queue schema is properly installed."""
    
    try:
        if database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        
        conn = await asyncpg.connect(database_url)
        
        # Check if table exists
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'dead_letter_queue')"
        )
        
        if not table_exists:
            print("✗ Dead letter queue table not found")
            await conn.close()
            return False
        
        # Check trigger exists
        trigger_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.triggers 
                WHERE trigger_name = 'archive_failed_job_trigger'
            )
        """)
        
        if not trigger_exists:
            print("✗ Archive trigger not found")
            await conn.close()
            return False
        
        # Check functions exist
        functions = [
            "archive_to_dead_letter_queue",
            "reprocess_dead_letter_entry",
            "get_dead_letter_stats",
        ]
        
        for func in functions:
            func_exists = await conn.fetchval(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.routines 
                    WHERE routine_name = '{func}'
                )
            """)
            
            if not func_exists:
                print(f"✗ Function {func} not found")
                await conn.close()
                return False
        
        await conn.close()
        print("✓ Dead letter queue schema verification passed!")
        return True
        
    except Exception as e:
        print(f"✗ Error verifying dead letter queue schema: {e}")
        return False


if __name__ == "__main__":
    # Get database URL from environment variable
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL to your PostgreSQL connection string")
        exit(1)
    
    # Run the async functions
    print("=" * 60)
    print("Dead Letter Queue Schema Setup")
    print("=" * 60)
    
    # Apply schema
    success = asyncio.run(apply_dead_letter_schema(database_url))
    
    if success:
        # Verify schema
        print("\n" + "=" * 60)
        print("Verifying Dead Letter Queue Schema")
        print("=" * 60)
        verification_success = asyncio.run(verify_dead_letter_schema(database_url))
        
        if verification_success:
            print("\n✅ Dead letter queue setup completed successfully!")
            print("\nFeatures installed:")
            print("  • dead_letter_queue table for permanent failure storage")
            print("  • Automatic archiving of failed jobs via trigger")
            print("  • Reprocessing functions for manual intervention")
            print("  • Statistical analysis functions")
            print("  • Circuit breaker integration in worker")
            print("  • API endpoints for management")
        else:
            print("\n❌ Dead letter queue schema verification failed!")
            exit(1)
    else:
        print("\n❌ Dead letter queue schema application failed!")
        exit(1)