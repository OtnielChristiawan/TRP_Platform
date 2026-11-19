import duckdb

def main():
    con = duckdb.connect()
    con.execute("LOAD httpfs;")
    con.execute("""
        CREATE OR REPLACE PERSISTENT SECRET minio_secret (
            TYPE S3,
            KEY_ID 'bakeryadmin',
            SECRET 'bakerydemo123',
            ENDPOINT 'localhost:9000',
            URL_STYLE 'path',
            USE_SSL false,
            REGION 'us-east-1'
        );
    """)
    print("SUCCESS: DuckDB persistent secret created successfully!")

if __name__ == "__main__":
    main()
