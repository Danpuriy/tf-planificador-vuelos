"""Configuración de pytest.

Agrega la carpeta `app/` al path para poder importar `algoritmos`,
`cargador_datos` y `servidor` desde las pruebas.
"""

import sys
from pathlib import Path

DIR_APP = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(DIR_APP))
