:: Replace USER_NAME with your own user name

SET FICHIER="C:\Users\USER_NAME\AppData\Local\Temp\www.srrdb.com_session.dat"

IF EXIST %FICHIER% DEL /F %FICHIER%
