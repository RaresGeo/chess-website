from django.shortcuts import render, redirect
from django.db import IntegrityError
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.password_validation import validate_password
from email_validator import validate_email, EmailNotValidError
from django.core.exceptions import ValidationError
import json
import random

from .models import User, ChessGame, PlayedGame


def home(request):
    # return redirect(request, "chess_content/memory_rush.html")
    return HttpResponseRedirect(reverse("memory_rush"))

def game_history(request):
    seen_games = PlayedGame.objects.filter(user=request.user).select_related('chess_game').order_by('-played_at')

    fen_data = [
        {
            'fen_string': game.chess_game.fen_string,
            'success': game.success,
            'played_at': game.played_at,
            'game_is_on': game.game_is_on,
            'error_count': game.error_count,
            'gotCorrectRoundNumber': game.gotCorrectRoundNumber,
            'chosenDifficulty': game.chosenDifficulty,
        }
        for game in seen_games
    ]

    return render(request, "chess_content/game_history.html", 
                  {'fen_data': fen_data})

@csrf_exempt
def memory_rush(request):
    white_piece_filenames = ['wk.png', 'wq.png', 'wr.png', 'wb.png', 'wn.png', 'wp.png']
    black_piece_filenames=  ['bk.png', 'bq.png', 'br.png', 'bb.png', 'bn.png', 'bp.png']
    video_names = ['easy', 'medium', 'hard']

    message = request.session.get('message', None)
    message_type = request.session.get('message_type', None)

    if message: 
        del request.session['message']
    if message_type:
        del request.session['message_type']

    return render(request, 'chess_content/memory_rush.html', 
                  {'black_piece_filenames': black_piece_filenames,
                   'white_piece_filenames': white_piece_filenames,
                   'video_names': video_names,
                   'message': message,
                   'message_type': message_type 
                   })

DIFFICULTIES = {
    'easy': {'countdown': 10, 'round': 10},
    'medium': {'countdown': 5, 'round': 5},
    'hard': {'countdown': 3, 'round': 3},
}

@csrf_exempt
def post_start_game(request):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.info(request, "You have to log in to play.")
            return JsonResponse({'status': 'unauthenticated'}, status=401)
        
        data = json.loads(request.body.decode('utf-8'))
        user = request.user
        chosenDifficulty = data['chosenDifficulty']
        
        # Check if the user has any games with game_is_on=True and matching chosenDifficulty
        ongoing_games = PlayedGame.objects.filter(user=user, game_is_on=True, chosenDifficulty=chosenDifficulty)
        random_FEN = None
        error_count = 0

        # If no ongoing games exist, proceed with creating a new game.
        if not ongoing_games.exists():
            # Get random unseen ChessGame's FEN string for the user
            fen_list = [game.fen_string for game in ChessGame.objects.exclude(
                id__in=PlayedGame.objects.filter(user=request.user).values_list('chess_game_id', flat=True)
            )]
            random_FEN = random.choice(fen_list) if fen_list else None
            chess_game = ChessGame.objects.get(fen_string=random_FEN)
            round_number = DIFFICULTIES.get(chosenDifficulty, {}).get('round', 'unknown')
            ongoing_game = PlayedGame.objects.create(
                user=user, 
                chess_game=chess_game, 
                success=False,
                game_is_on=True,
                round_number=round_number,
                error_count=error_count,
                chosenDifficulty=chosenDifficulty,
                fen_str=random_FEN
            )
        else:
            # Retrieve fen_str from the ongoing game
            ongoing_game = ongoing_games.filter(chosenDifficulty=chosenDifficulty).first()
            
            random_FEN = ongoing_game.fen_str
            error_count = ongoing_game.error_count

        error_for_json = error_count
        countdown = DIFFICULTIES.get(chosenDifficulty, {}).get('countdown', 'unknown')
        round_number = DIFFICULTIES.get(chosenDifficulty, {}).get('round', 'unknown')

        # Increment the error count by 1 to account for potential game abandonment by the user
        request.session['game_fen'] = ongoing_game.fen_str
        ongoing_game.error_count += 1
        ongoing_game.save()
        if (ongoing_game.error_count == ongoing_game.round_number):
            ongoing_game.success = False
            ongoing_game.game_is_on = False
            ongoing_game.save()

        return JsonResponse({
            'countdown': countdown,
            'round': round_number,
            'random_FEN': random_FEN,
            'error_count': error_for_json
        })

def put_submit_game(request):
    if request.method == 'PUT':
        user = request.user
        data = json.loads(request.body.decode('utf-8'))
        pieces_by_user = data['piecesByUser']
        chosenDifficulty = data['chosenDifficulty']

        # User sent a PUT request; decrement the error count by 1 to reverse the previous increment meant for handling game abandonment
        game_fen = request.session.get('game_fen')
        if game_fen:
            game = PlayedGame.objects.filter(user=user, fen_str=game_fen).first()
            if game:
                if game.error_count == game.round_number:
                    game.game_is_on = True
                    game.save()
                game.error_count -= 1
                game.save()

        ongoing_games = PlayedGame.objects.filter(user=user, game_is_on=True, chosenDifficulty=chosenDifficulty)
        ongoing_game = ongoing_games.filter(chosenDifficulty=chosenDifficulty).first()
        fen_str = ongoing_game.fen_str
        error_count = ongoing_game.error_count
        chosenDifficulty = ongoing_game.chosenDifficulty
        round_number = DIFFICULTIES.get(chosenDifficulty, {}).get('round', 'unknown')

        transformed_data = []

        for piece_info in pieces_by_user:
            piece_name = piece_info['name']
            left = piece_info['left']
            top = piece_info['top']
            mobileView = piece_info['mobileView']
            square = position_to_square(left, top, mobileView)
            transformed_data.append({'name': piece_name, 'square': square})

        fen_position_sorted = fen_to_board(fen_str)
        transformed_data_sorted = sorted(transformed_data, key=lambda x: (x['square'], x['name']))
        
        # Sort fen_position_sorted before comparison
        fen_position_sorted = sorted(fen_position_sorted, key=lambda x: (x['square'], x['name']))

        # If the user piece positions are correct
        if fen_position_sorted == transformed_data_sorted:
            ongoing_game.success = True
            ongoing_game.game_is_on = False
            ongoing_game.gotCorrectRoundNumber = error_count + 1
            ongoing_game.save()
            if 'game_fen' in request.session:
                del request.session['game_fen']
            return HttpResponseRedirect(reverse("memory_rush"))
        else:
            # If the user piece positions are wrong and has no tries left
            if (error_count + 1 == round_number):
                ongoing_game.success = False
                ongoing_game.game_is_on = False
                ongoing_game.error_count = error_count + 1
                ongoing_game.save()
                if 'game_fen' in request.session:
                    del request.session['game_fen']
                return HttpResponse(status=403)
            else:
            # If the user piece positions are wrong and still has tries left
                ongoing_game.game_is_on = True
                ongoing_game.success = False
                ongoing_game.error_count = error_count + 1
                ongoing_game.save()
                if 'game_fen' in request.session:
                    del request.session['game_fen']
                return HttpResponse(status=400)

def fen_to_board(fen):
    board_str, to_move, castling, en_passant, halfmove, fullmove = fen.split(' ')
    
    rows = board_str.split('/')
    board = []
    row_labels = list(range(8, 0, -1))
    col_labels = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    
    for row_index, row in enumerate(rows):
        col_index = 0
        for char in row:
            if char.isdigit():
                col_index += int(char)
            else:
                square = col_labels[col_index] + str(row_labels[row_index])
                piece = ""
                if char == 'r':
                    piece = "br.png"
                elif char == 'n':
                    piece = "bn.png"
                elif char == 'b':
                    piece = "bb.png"
                elif char == 'q':
                    piece = "bq.png"
                elif char == 'k':
                    piece = "bk.png"
                elif char == 'p':
                    piece = "bp.png"
                elif char == 'R':
                    piece = "wr.png"
                elif char == 'N':
                    piece = "wn.png"
                elif char == 'B':
                    piece = "wb.png"
                elif char == 'Q':
                    piece = "wq.png"
                elif char == 'K':
                    piece = "wk.png"
                elif char == 'P':
                    piece = "wp.png"
                
                board.append({'name': piece, 'square': square})
                col_index += 1
                
    return board

def position_to_square(left, top, mobileView):
    if (mobileView == True):
        pieceSize = 50
    elif (mobileView == False):
        pieceSize = 90
    # Calculate the column (letter) based on the left position
    column = chr(ord('a') + (left // pieceSize))
    
    # Calculate the row (number) based on the top position
    row = 8 - (top // pieceSize)
    
    return f'{column}{row}'

def login_view(request):
    if request.method == "POST":    
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Successfully logged in.")
            return HttpResponseRedirect(reverse("home"))
        else:
            messages.error(request, "Invalid username and/or password.")
            return HttpResponseRedirect(reverse('login'))
    else:
        return render(request, "chess_content/login.html")

def logout_view(request):
    logout(request)
    messages.info(request, "Logged out.")
    return HttpResponseRedirect(reverse("home"))

def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        try:
            validate_password(password)
        except ValidationError as e:
            messages.error(request, str(e))
            return HttpResponseRedirect(reverse('register'))
        try:
            validate_email(email)
        except EmailNotValidError as e:
            messages.error(request, str(e))
            return HttpResponseRedirect(reverse('register'))
        
        if password != confirmation:
            messages.error(request, "Passwords must match.")
            return HttpResponseRedirect(reverse('register'))
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            messages.error(request, "Username already taken.")
            return HttpResponseRedirect(reverse('register'))
        login(request, user)
        messages.success(request, "Registration successful.")
        return HttpResponseRedirect(reverse("home"))
    else:
        return render(request, "chess_content/register.html")
