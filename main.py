"""Browser entry for pygbag. Also runs with: python main.py"""

import asyncio
import pygame
import pygame.mixer

from shooter.game import main

asyncio.run(main())
