from datetime import datetime, date, timedelta
import random

class Character:
    """
    Character domain model - contains only business logic, no database code
    """
    def __init__(self, discord_id: int, level: int = 1, last_attempt: datetime = None, 
                 last_successful_levelup: date = None):
        self._discordId = discord_id
        self._level = level
        self._lastAttempt = last_attempt
        self._lastSuccessfulLevelup = last_successful_levelup  # Date only, not datetime
   
    # Getters
    def get_discord_id(self) -> int:
        return self._discordId
    
    def get_level(self) -> int:
        return self._level
    
    def get_last_attempt(self) -> datetime:
        return self._lastAttempt
   
    def get_last_successful_levelup(self) -> date:
        return self._lastSuccessfulLevelup
    
    # Business Logic
    def can_attempt_levelup(self, cooldown_hours: int = 1, has_swim_bonus: bool = False, has_chaussette_bonus: bool = False) -> tuple[bool, str]:
        """
        Check if user can attempt levelup
        has_swim_bonus: If True, bypasses all cooldowns
        Returns: (can_attempt: bool, message: str)
        """
        # Swim bonus bypasses all checks
        if has_swim_bonus:
            return True, "Bonus Nage actif !"
        
        # Chaussette bonus bypasses all checks
        if has_chaussette_bonus:
            return True, "Bonus Chaussette actif !"
        
        today = date.today()
        
        # Check attempt cooldown first (1 hour between ANY attempts)
        if self._lastAttempt:
            now = datetime.now()
            time_since_last = now - self._lastAttempt
            cooldown = timedelta(hours=cooldown_hours)
            
            if time_since_last < cooldown:
                remaining_minutes = (cooldown - time_since_last).seconds // 60
                remaining_seconds = (cooldown - time_since_last).seconds % 60
                
                if remaining_minutes > 0:
                    return False, f"Attendez encore {remaining_minutes} minute(s) et {remaining_seconds} seconde(s) avant de réessayer."
                else:
                    return False, f"Attendez encore {remaining_seconds} seconde(s) avant de réessayer."
        
        # Then check if already leveled up successfully today (prevents multiple successes per day)
        if self._lastSuccessfulLevelup and self._lastSuccessfulLevelup >= today:
            return False, "Vous avez déjà réussi un level up aujourd'hui ! Revenez demain."
        
        return True, "Prêt !"
    
    def calculate_success_chance(self, base_chance: int = 20, bonus_per_hour: int = 5, 
                                 max_chance: int = 80) -> float:
        """
        Calculate success chance based on time since last attempt
        """
        if not self._lastAttempt:
            return base_chance
        
        now = datetime.now()
        hours_since_last = (now - self._lastAttempt).total_seconds() / 3600
        
        # Add bonus per hour waited, cap at max_chance
        bonus = min(hours_since_last * bonus_per_hour, max_chance - base_chance)
        return min(base_chance + bonus, max_chance)
    
    def attempt_to_levelup(self, base_chance: int = 20, bonus_per_hour: int = 5, 
                          max_chance: int = 80, cooldown_hours: int = 1, has_swim_bonus: bool = False, has_chaussette_bonus: bool = False) -> tuple[bool, str, float]:
        """
        Attempt to level up the character
        has_swim_bonus: If True, bypasses cooldown checks
        Returns: (success: bool, message: str, probability: float)
        """
        can_attempt, msg = self.can_attempt_levelup(cooldown_hours, has_swim_bonus, has_chaussette_bonus)
        if not can_attempt:
            return False, msg, 0
        
        now = datetime.now()
        self._lastAttempt = now
        
        probability = self.calculate_success_chance(base_chance, bonus_per_hour, max_chance)
        success = random.random() < (probability / 100.0)
        
        if success:
            self._level_up()
            return True, f"Succès ! Vous êtes maintenant niveau {self._level} ! 🎉", probability
        else:
            return False, f"Échec... Retentez votre chance plus tard ! ({probability:.1f}% de chance)", probability
    
    def _level_up(self):
        """Internal method to increase level"""
        self._level += 1
        self._lastSuccessfulLevelup = date.today()
    
    def to_dict(self) -> dict:
        """Convert character to dictionary for serialization"""
        return {
            'discord_id': self._discordId,
            'level': self._level,
            'last_attempt': self._lastAttempt,
            'last_successful_levelup': self._lastSuccessfulLevelup
        }