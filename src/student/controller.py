from collections import deque
from typing import Iterable, Optional, Set, Tuple

from src.api import Position, WorldAction, WorldActionType, WorldSnapshot


_MOVES: Tuple[Tuple[int, int, WorldActionType], ...] = (
    (-1, 0, WorldActionType.MOVE_NORTH),
    (1, 0, WorldActionType.MOVE_SOUTH),
    (0, -1, WorldActionType.MOVE_WEST),
    (0, 1, WorldActionType.MOVE_EAST),
)


def _shortest_route(
    state: WorldSnapshot,
    goal: Position,
    blocked: Set[Position],
    allowed_actions: Set[WorldActionType],
) -> Optional[Tuple[WorldAction, int]]:
    """
    Return the first action toward a goal and the route distance.

    Returns None when no route exists.
    """
    start = state.agent_position

    if start == goal:
        return None

    queue = deque([(start, None, 0)])
    visited = {start}

    while queue:
        position, first_action, distance = queue.popleft()

        for row_delta, column_delta, action_type in _MOVES:
            if action_type not in allowed_actions:
                continue

            neighbor = Position(
                position.row + row_delta,
                position.column + column_delta,
            )

            if neighbor in visited:
                continue
            if neighbor in blocked:
                continue
            if not state.terrain.is_traversable(neighbor):
                continue

            next_action = first_action or WorldAction(action_type)
            next_distance = distance + 1

            if neighbor == goal:
                return next_action, next_distance

            visited.add(neighbor)
            queue.append((neighbor, next_action, next_distance))

    return None


class AgentController:
    """Plans actions from each public world snapshot."""

    def __init__(self) -> None:
        pass

    def choose_action(
        self,
        state: WorldSnapshot,
        agent_id: str,
    ) -> WorldAction:
        allowed_actions = set(state.allowed_actions)
        living_enemies = self._living_enemies(state)
        blocked_positions = {
            enemy.position
            for enemy in living_enemies
        }

        action = self._collect_artifact_at_current_position(
            state,
            allowed_actions,
        )
        if action is not None:
            return action

        action = self._exit_at_exit_position(
            state,
            allowed_actions,
        )
        if action is not None:
            return action

        action = self._move_to_nearest_reachable_artifact(
            state,
            blocked_positions,
            allowed_actions,
        )
        if action is not None:
            return action

        action = self._move_to_artifact_by_engaging_enemy(
            state,
            living_enemies,
            blocked_positions,
            allowed_actions,
        )
        if action is not None:
            return action

        action = self._move_to_exit_by_engaging_enemy(
            state,
            living_enemies,
            blocked_positions,
            allowed_actions,
        )
        if action is not None:
            return action

        if WorldActionType.WAIT in allowed_actions:
            return WorldAction.wait()

        raise ValueError("No route or valid action is available.")

    @staticmethod
    def _living_enemies(state: WorldSnapshot) -> list:
        """Return enemies that have not been defeated."""
        return [
            enemy
            for enemy in state.level.enemies
            if enemy.enemy_id not in state.defeated_enemy_ids
        ]

    @staticmethod
    def _collect_artifact_at_current_position(
        state: WorldSnapshot,
        allowed_actions: Set[WorldActionType],
    ) -> Optional[WorldAction]:
        """Collect an uncollected artifact on the current tile."""
        if WorldActionType.COLLECT not in allowed_actions:
            return None

        for artifact in state.level.artifacts:
            if (
                artifact.position == state.agent_position
                and artifact.artifact_id not in state.collected_artifact_ids
            ):
                return WorldAction(
                    WorldActionType.COLLECT,
                    target_id=artifact.artifact_id,
                )

        return None

    @staticmethod
    def _exit_at_exit_position(
        state: WorldSnapshot,
        allowed_actions: Set[WorldActionType],
    ) -> Optional[WorldAction]:
        """Exit explicitly when standing on the exit."""
        if (
            state.agent_position == state.exit_position
            and WorldActionType.EXIT in allowed_actions
        ):
            return WorldAction(WorldActionType.EXIT)

        return None

    @staticmethod
    def _move_to_nearest_reachable_artifact(
        state: WorldSnapshot,
        blocked_positions: Set[Position],
        allowed_actions: Set[WorldActionType],
    ) -> Optional[WorldAction]:
        """Move toward the closest artifact reachable without combat."""
        reachable_artifacts = []

        for artifact in state.level.artifacts:
            if artifact.artifact_id in state.collected_artifact_ids:
                continue

            route = _shortest_route(
                state,
                artifact.position,
                blocked_positions,
                allowed_actions,
            )

            if route is not None:
                action, distance = route
                reachable_artifacts.append((distance, action))

        if not reachable_artifacts:
            return None

        _, closest_action = min(
            reachable_artifacts,
            key=lambda item: item[0],
        )
        return closest_action

    def _move_to_artifact_by_engaging_enemy(
        self,
        state: WorldSnapshot,
        living_enemies: Iterable,
        blocked_positions: Set[Position],
        allowed_actions: Set[WorldActionType],
    ) -> Optional[WorldAction]:
        """Move toward or engage an enemy blocking an uncollected artifact."""
        remaining_artifacts = [
            artifact
            for artifact in state.level.artifacts
            if artifact.artifact_id not in state.collected_artifact_ids
        ]

        remaining_artifacts.sort(
            key=lambda artifact: state.agent_position.manhattan_distance(
                artifact.position
            )
        )

        for artifact in remaining_artifacts:
            action = self._plan_route_with_enemy(
                state,
                artifact.position,
                living_enemies,
                blocked_positions,
                allowed_actions,
            )
            if action is not None:
                return action

        return None

    def _move_to_exit_by_engaging_enemy(
        self,
        state: WorldSnapshot,
        living_enemies: Iterable,
        blocked_positions: Set[Position],
        allowed_actions: Set[WorldActionType],
    ) -> Optional[WorldAction]:
        """Move toward or engage an enemy blocking the exit."""
        return self._plan_route_with_enemy(
            state,
            state.exit_position,
            living_enemies,
            blocked_positions,
            allowed_actions,
        )

    def _plan_route_with_enemy(
        self,
        state: WorldSnapshot,
        goal: Position,
        living_enemies: Iterable,
        blocked_positions: Set[Position],
        allowed_actions: Set[WorldActionType],
    ) -> Optional[WorldAction]:
        """
        Find a route to a goal, or engage an enemy whose removal opens it.

        Returns None when no such route or enemy is available.
        """
        route = _shortest_route(
            state,
            goal,
            blocked_positions,
            allowed_actions,
        )
        if route is not None:
            action, _distance = route
            return action

        if WorldActionType.ENGAGE not in allowed_actions:
            return None

        for enemy in living_enemies:
            if not self._removing_enemy_opens_route(
                state,
                goal,
                enemy,
                living_enemies,
                blocked_positions,
                allowed_actions,
            ):
                continue

            action = self._move_to_enemy(
                state,
                enemy,
                blocked_positions,
                allowed_actions,
            )
            if action is not None:
                return action

        return None

    @staticmethod
    def _removing_enemy_opens_route(
        state: WorldSnapshot,
        goal: Position,
        enemy,
        living_enemies: Iterable,
        blocked_positions: Set[Position],
        allowed_actions: Set[WorldActionType],
    ) -> bool:
        """Check whether removing an enemy makes the goal reachable."""
        del blocked_positions  # Kept explicit in the public plan for clarity.

        other_blockers = {
            other.position
            for other in living_enemies
            if other.enemy_id != enemy.enemy_id
        }

        return _shortest_route(
            state,
            goal,
            other_blockers,
            allowed_actions,
        ) is not None

    def _move_to_enemy(
        self,
        state: WorldSnapshot,
        enemy,
        blocked_positions: Set[Position],
        allowed_actions: Set[WorldActionType],
    ) -> Optional[WorldAction]:
        """Engage an adjacent enemy or move toward an adjacent approach tile."""
        position = state.agent_position

        if position.manhattan_distance(enemy.position) == 1:
            return WorldAction(
                WorldActionType.ENGAGE,
                target_id=enemy.enemy_id,
            )

        approaches = []

        for row_delta, column_delta, _action_type in _MOVES:
            neighbor = Position(
                enemy.position.row + row_delta,
                enemy.position.column + column_delta,
            )

            if not state.terrain.is_traversable(neighbor):
                continue
            if neighbor in blocked_positions:
                continue

            route = _shortest_route(
                state,
                neighbor,
                blocked_positions,
                allowed_actions,
            )
            if route is not None:
                action, distance = route
                approaches.append((distance, action))

        if not approaches:
            return None

        _, shortest_action = min(
            approaches,
            key=lambda item: item[0],
        )
        return shortest_action
