from flask_mysqldb import MySQL

# Create a MySQL object
mysql = MySQL()


def init_db(app):
    """
    Initialize MySQL with the Flask application.
    """
    mysql.init_app(app)