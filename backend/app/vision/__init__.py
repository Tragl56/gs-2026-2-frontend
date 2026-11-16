"""Módulo de visão computacional da Zela: triagem de fissuras em concreto por foto ou vídeo.

O modelo (ResNet18 com transferência de aprendizado, treinado no notebook do projeto de Visão
Computacional) roda só no back-end. Dependências pesadas (PyTorch, OpenCV) ficam em
`requirements-vision.txt`; sem elas a API continua no ar e os endpoints de visão respondem 503.
"""
