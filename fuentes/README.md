Carpeta de archivos fuente de datos (.xlsx).

Las bases de datos del modelo (data/*.db) ya estan generadas e
incluidas en el repositorio, por lo que el programa funciona sin
necesidad de estos archivos.

Para regenerar las bases desde los archivos fuente de datos, coloque
los .xlsx en esta carpeta y ejecute:

    python scripts/migrar_xlsx.py

Los .xlsx no se versionan por su tamano.
