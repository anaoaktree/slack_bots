import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Database URL determination
    @staticmethod
    def get_database_url():
        """Return appropriate database URL based on environment."""
        # Check if MySQL environment variables are set (production)
        mysql_host = os.environ.get('MYSQL_HOST')
        mysql_user = os.environ.get('MYSQL_USER')
        mysql_password = os.environ.get('MYSQL_PASSWORD')
        mysql_db = os.environ.get('MYSQL_DATABASE')
        
        if all([mysql_host, mysql_user, mysql_password, mysql_db]):
            # Production MySQL
            return f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}/{mysql_db}'
        else:
            # Local development SQLite
            basedir = os.path.abspath(os.path.dirname(__file__))
            return f'sqlite:///{os.path.join(basedir, "ab_testing.db")}'
    
    SQLALCHEMY_DATABASE_URI = get_database_url()


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 