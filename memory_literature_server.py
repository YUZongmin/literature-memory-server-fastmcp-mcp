from pathlib import Path
import sqlite3
import os
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple, Set
from fastmcp import FastMCP
from datetime import datetime
import re

# Initialize FastMCP server
mcp = FastMCP("Source Manager")

# Path to Literature database - must be provided via SQLITE_DB_PATH environment variable
if 'SQLITE_DB_PATH' not in os.environ:
    raise ValueError("SQLITE_DB_PATH environment variable must be set")
DB_PATH = Path(os.environ['SQLITE_DB_PATH'])



# Core type definitions
class Entity:
    def __init__(self, name: str, entity_type: str, observations: List[str]):
        self.name = name
        self.entityType = entity_type
        self.observations = observations

class Relation:
    def __init__(self, from_entity: str, to_entity: str, relation_type: str):
        self.from_entity = from_entity
        self.to_entity = to_entity
        self.relationType = relation_type

class KnowledgeGraph:
    def __init__(self):
        self.entities: List[Entity] = []
        self.relations: List[Relation] = []



# Core classes for source management
class SourceTypes:
    VALID_TYPES = {'paper', 'webpage', 'book', 'video', 'blog'}

class SourceStatus:
    VALID_STATUS = {'unread', 'reading', 'completed', 'archived'}

class SourceIdentifiers:
    VALID_TYPES = {'semantic_scholar', 'arxiv', 'doi', 'isbn', 'url'}

class EntityRelations:
    VALID_TYPES = {'discusses', 'introduces', 'extends', 'evaluates', 'applies', 'critiques'}




class SQLiteConnection:
    """Context manager for SQLite database connections"""
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = None
        
    def __enter__(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        return self.conn
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()


class KnowledgeGraphManager:
    """Manages operations on the knowledge graph"""
    def __init__(self, memory_file_path: Path):
        self.memory_file_path = memory_file_path
        
    def _load_graph(self) -> KnowledgeGraph:
        """Load the knowledge graph from file"""
        try:
            with open(self.memory_file_path, 'r') as f:
                data = f.read()
                if not data:
                    return KnowledgeGraph()
                    
                lines = data.split("\n")
                graph = KnowledgeGraph()
                
                for line in lines:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get('type') == 'entity':
                        entity = Entity(
                            name=item['name'],
                            entity_type=item['entityType'],
                            observations=item['observations']
                        )
                        graph.entities.append(entity)
                    elif item.get('type') == 'relation':
                        relation = Relation(
                            from_entity=item['from'],
                            to_entity=item['to'],
                            relation_type=item['relationType']
                        )
                        graph.relations.append(relation)
                return graph
        except FileNotFoundError:
            return KnowledgeGraph()
    
    def _save_graph(self, graph: KnowledgeGraph):
        """Save the knowledge graph to file"""
        lines = []
        for entity in graph.entities:
            lines.append(json.dumps({
                'type': 'entity',
                'name': entity.name,
                'entityType': entity.entityType,
                'observations': entity.observations
            }))
        for relation in graph.relations:
            lines.append(json.dumps({
                'type': 'relation',
                'from': relation.from_entity,
                'to': relation.to_entity,
                'relationType': relation.relationType
            }))
        
        with open(self.memory_file_path, 'w') as f:
            f.write('\n'.join(lines))

    def create_entities(self, entities: List[Dict]) -> List[Entity]:
        """Create multiple new entities in the knowledge graph"""
        graph = self._load_graph()
        new_entities = []
        
        for entity_data in entities:
            # Check if entity already exists
            if not any(e.name == entity_data['name'] for e in graph.entities):
                entity = Entity(
                    name=entity_data['name'],
                    entity_type=entity_data['entityType'],
                    observations=entity_data['observations']
                )
                graph.entities.append(entity)
                new_entities.append(entity)
        
        self._save_graph(graph)
        return new_entities

    def create_relations(self, relations: List[Dict]) -> List[Relation]:
        """Create multiple new relations between entities"""
        graph = self._load_graph()
        new_relations = []
        
        for relation_data in relations:
            # Check if relation already exists
            exists = any(
                r.from_entity == relation_data['from'] and
                r.to_entity == relation_data['to'] and
                r.relationType == relation_data['relationType']
                for r in graph.relations
            )
            if not exists:
                relation = Relation(
                    from_entity=relation_data['from'],
                    to_entity=relation_data['to'],
                    relation_type=relation_data['relationType']
                )
                graph.relations.append(relation)
                new_relations.append(relation)
        
        self._save_graph(graph)
        return new_relations

    def add_observations(self, observations: List[Dict]) -> List[Dict]:
        """Add new observations to existing entities"""
        graph = self._load_graph()
        results = []
        
        for obs in observations:
            entity_name = obs['entityName']
            contents = obs['contents']
            
            # Find the entity
            entity = next((e for e in graph.entities if e.name == entity_name), None)
            if not entity:
                raise ValueError(f"Entity with name {entity_name} not found")
            
            # Add new observations
            new_observations = [
                content for content in contents
                if content not in entity.observations
            ]
            entity.observations.extend(new_observations)
            
            results.append({
                'entityName': entity_name,
                'addedObservations': new_observations
            })
        
        self._save_graph(graph)
        return results

    def delete_entities(self, entity_names: List[str]):
        """Delete multiple entities and their associated relations"""
        graph = self._load_graph()
        
        # Remove entities
        graph.entities = [
            e for e in graph.entities 
            if e.name not in entity_names
        ]
        
        # Remove associated relations
        graph.relations = [
            r for r in graph.relations
            if r.from_entity not in entity_names and r.to_entity not in entity_names
        ]
        
        self._save_graph(graph)

    def delete_observations(self, deletions: List[Dict]):
        """Delete specific observations from entities"""
        graph = self._load_graph()
        
        for deletion in deletions:
            entity_name = deletion['entityName']
            observations_to_delete = deletion['observations']
            
            # Find and update entity
            entity = next((e for e in graph.entities if e.name == entity_name), None)
            if entity:
                entity.observations = [
                    obs for obs in entity.observations
                    if obs not in observations_to_delete
                ]
        
        self._save_graph(graph)

    def delete_relations(self, relations: List[Dict]):
        """Delete specific relations from the graph"""
        graph = self._load_graph()
        
        graph.relations = [
            r for r in graph.relations
            if not any(
                r.from_entity == rel['from'] and
                r.to_entity == rel['to'] and
                r.relationType == rel['relationType']
                for rel in relations
            )
        ]
        
        self._save_graph(graph)

    def read_graph(self) -> KnowledgeGraph:
        """Read the entire knowledge graph"""
        return self._load_graph()

    def search_nodes(self, query: str) -> KnowledgeGraph:
        """Search for nodes based on query"""
        graph = self._load_graph()
        query_lower = query.lower()
        
        # Filter entities
        filtered_entities = [
            e for e in graph.entities
            if (query_lower in e.name.lower() or
                query_lower in e.entityType.lower() or
                any(query_lower in obs.lower() for obs in e.observations))
        ]
        
        # Get names of filtered entities for relation filtering
        filtered_names = {e.name for e in filtered_entities}
        
        # Filter relations to only include those between filtered entities
        filtered_relations = [
            r for r in graph.relations
            if r.from_entity in filtered_names and r.to_entity in filtered_names
        ]
        
        result = KnowledgeGraph()
        result.entities = filtered_entities
        result.relations = filtered_relations
        return result

    def open_nodes(self, names: List[str]) -> KnowledgeGraph:
        """Retrieve specific nodes by name"""
        graph = self._load_graph()
        
        # Filter entities
        filtered_entities = [
            e for e in graph.entities
            if e.name in names
        ]
        
        # Get filtered entity names for relation filtering
        filtered_names = {e.name for e in filtered_entities}
        
        # Filter relations to only include those between filtered entities
        filtered_relations = [
            r for r in graph.relations
            if r.from_entity in filtered_names and r.to_entity in filtered_names
        ]
        
        result = KnowledgeGraph()
        result.entities = filtered_entities
        result.relations = filtered_relations
        return result


class IntegratedSourceManager:
    """Manages both source database and knowledge graph operations"""
    def __init__(self, db_path: Path, memory_file_path: Path):
        self.db_path = db_path
        self.kg_manager = KnowledgeGraphManager(memory_file_path)
        
    def search_source(self, title: str, type: str, identifier_type: str, 
                     identifier_value: str) -> Tuple[Optional[str], List[Dict]]:
        """Search for a source in the database"""
        # Implementation remains the same as in original server
        pass
        
    def get_source_details(self, uuid: str) -> Dict:
        """Get complete source information"""
        # Implementation remains the same as in original server
        pass
        
    def link_source_to_entity(self, source_id: str, entity_name: str, 
                            relation_type: str, notes: Optional[str] = None) -> Dict:
        """Create bidirectional link between source and entity"""
        # Implementation for integrated linking
        pass




# Core Helper Functions

def search_source(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str,
    db_path: Path
) -> Tuple[Optional[str], List[Dict]]:
    """
    Core search function for finding sources in the database.
    
    Args:
        title: Source title
        type: Source type (must be in SourceTypes.VALID_TYPES)
        identifier_type: Type of identifier (must be in SourceIdentifiers.VALID_TYPES)
        identifier_value: Value of the identifier
        db_path: Path to SQLite database
        
    Returns:
        Tuple containing:
        - UUID of exact match if found by identifier (else None)
        - List of potential matches by title/type (empty if exact match found)
        
    Raises:
        ValueError: If invalid type or identifier_type provided
    """
    # Validate inputs
    if type not in SourceTypes.VALID_TYPES:
        raise ValueError(f"Invalid source type. Must be one of: {SourceTypes.VALID_TYPES}")
        
    if identifier_type not in SourceIdentifiers.VALID_TYPES:
        raise ValueError(f"Invalid identifier type. Must be one of: {SourceIdentifiers.VALID_TYPES}")
    
    with SQLiteConnection(db_path) as conn:
        cursor = conn.cursor()
        
        # First try exact identifier match
        cursor.execute("""
            SELECT id FROM sources
            WHERE type = ? AND 
                  json_extract(identifiers, ?) = ?
        """, [
            type,
            f"$.{identifier_type}",
            identifier_value
        ])
        
        result = cursor.fetchone()
        if result:
            return result['id'], []
            
        # If no exact match, try fuzzy title match with same type
        cursor.execute("""
            SELECT id, title, identifiers
            FROM sources
            WHERE type = ? AND 
                  LOWER(title) LIKE ?
        """, [
            type,
            f"%{title.lower()}%"
        ])
        
        potential_matches = []
        for row in cursor.fetchall():
            match_data = {
                'id': row['id'],
                'title': row['title'],
                'identifiers': json.loads(row['identifiers'])
            }
            potential_matches.append(match_data)
            
        return None, potential_matches

def get_source_details(uuid: str, db_path: Path) -> Dict:
    """
    Get complete information about a source by UUID.
    
    Args:
        uuid: Source UUID
        db_path: Path to SQLite database
        
    Returns:
        Dictionary containing all source information:
        - Basic info (id, title, type, status, identifiers)
        - Notes (list of {title, content, created_at})
        - Entity links (list of {entity_name, relation_type, notes})
        
    Raises:
        ValueError: If source with UUID not found
    """
    with SQLiteConnection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get basic source info
        cursor.execute("""
            SELECT id, title, type, status, identifiers
            FROM sources
            WHERE id = ?
        """, [uuid])
        
        source = cursor.fetchone()
        if not source:
            raise ValueError(f"Source with UUID {uuid} not found")
            
        source_data = {
            'id': source['id'],
            'title': source['title'],
            'type': source['type'],
            'status': source['status'],
            'identifiers': json.loads(source['identifiers'])
        }
        
        # Get notes
        cursor.execute("""
            SELECT note_title, content, created_at
            FROM source_notes
            WHERE source_id = ?
            ORDER BY created_at DESC
        """, [uuid])
        
        source_data['notes'] = [
            {
                'title': row['note_title'],
                'content': row['content'],
                'created_at': row['created_at']
            }
            for row in cursor.fetchall()
        ]
        
        # Get entity links
        cursor.execute("""
            SELECT entity_name, relation_type, notes
            FROM source_entity_links
            WHERE source_id = ?
        """, [uuid])
        
        source_data['entity_links'] = [
            {
                'entity_name': row['entity_name'],
                'relation_type': row['relation_type'],
                'notes': row['notes']
            }
            for row in cursor.fetchall()
        ]
        
        return source_data

# Original tools for completeness for sqlite
@mcp.tool()
def read_query(
    query: str,
    params: Optional[List[Any]] = None,
    fetch_all: bool = True,
    row_limit: int = 1000
) -> List[Dict[str, Any]]:
    """Execute a query on the Literature database.
    
    Args:
        query: SELECT SQL query to execute
        params: Optional list of parameters for the query
        fetch_all: If True, fetches all results. If False, fetches one row.
        row_limit: Maximum number of rows to return (default 1000)
    
    Returns:
        List of dictionaries containing the query results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    query = query.strip()
    if query.endswith(';'):
        query = query[:-1].strip()
    
    def contains_multiple_statements(sql: str) -> bool:
        in_single_quote = False
        in_double_quote = False
        for char in sql:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == ';' and not in_single_quote and not in_double_quote:
                return True
        return False
    
    if contains_multiple_statements(query):
        raise ValueError("Multiple SQL statements are not allowed")
    
    query_lower = query.lower()
    if not any(query_lower.startswith(prefix) for prefix in ('select', 'with')):
        raise ValueError("Only SELECT queries (including WITH clauses) are allowed for safety")
    
    params = params or []
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            if 'limit' not in query_lower:
                query = f"{query} LIMIT {row_limit}"
            
            cursor.execute(query, params)
            
            if fetch_all:
                results = cursor.fetchall()
            else:
                results = [cursor.fetchone()]
                
            return [dict(row) for row in results if row is not None]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def list_tables() -> List[str]:
    """List all tables in the Literature database.
    
    Returns:
        List of table names in the database
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                ORDER BY name
            """)
            
            return [row['name'] for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def describe_table(table_name: str) -> List[Dict[str, str]]:
    """Get detailed information about a table's schema.
    
    Args:
        table_name: Name of the table to describe
        
    Returns:
        List of dictionaries containing column information:
        - name: Column name
        - type: Column data type
        - notnull: Whether the column can contain NULL values
        - dflt_value: Default value for the column
        - pk: Whether the column is part of the primary key
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            # Verify table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, [table_name])
            
            if not cursor.fetchone():
                raise ValueError(f"Table '{table_name}' does not exist")
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            return [dict(row) for row in columns]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_table_stats(table_name: str) -> Dict[str, Any]:
    """Get statistics about a table, including row count and storage info.
    
    Args:
        table_name: Name of the table to analyze
        
    Returns:
        Dictionary containing table statistics
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Verify table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, [table_name])
            
            if not cursor.fetchone():
                raise ValueError(f"Table '{table_name}' does not exist")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            row_count = cursor.fetchone()['count']
            
            # Get storage info
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = len(cursor.fetchall())
            
            return {
                "table_name": table_name,
                "row_count": row_count,
                "column_count": columns,
                "page_size": page_size
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_database_info() -> Dict[str, Any]:
    """Get overall database information and statistics.
    
    Returns:
        Dictionary containing database statistics and information
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get database size
            db_size = os.path.getsize(DB_PATH)
            
            # Get table counts
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            table_count = cursor.fetchone()['count']
            
            # Get SQLite version
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            
            # Get table statistics
            tables = {}
            cursor.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            
            for row in cursor.fetchall():
                table_name = row['name']
                cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                tables[table_name] = cursor.fetchone()['count']
            
            return {
                "database_size_bytes": db_size,
                "table_count": table_count,
                "sqlite_version": version,
                "table_row_counts": tables,
                "path": str(DB_PATH)
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def vacuum_database() -> Dict[str, Any]:
    """Optimize the database by running VACUUM command.
    This rebuilds the database file to reclaim unused space.
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get size before vacuum
            size_before = os.path.getsize(DB_PATH)
            
            # Run vacuum
            cursor.execute("VACUUM")
            
            # Get size after vacuum
            size_after = os.path.getsize(DB_PATH)
            
            return {
                "status": "success",
                "size_before_bytes": size_before,
                "size_after_bytes": size_after,
                "space_saved_bytes": size_before - size_after
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")



# Public tools

@mcp.tool()
def add_source(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str,
    initial_note: Optional[Dict[str, str]] = None  # {"title": "...", "content": "..."}
) -> Dict[str, Any]:
    """Add a new source with duplicate checking.
    
    Args:
        title: Source title
        type: Source type (paper, webpage, book, video, blog)
        identifier_type: Type of identifier (semantic_scholar, arxiv, doi, isbn, url)
        identifier_value: Value of the identifier
        initial_note: Optional initial note with title and content
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    # Validate source type
    if type not in SourceTypes.VALID_TYPES:
        raise ValueError(f"Invalid source type. Must be one of: {SourceTypes.VALID_TYPES}")
        
    # Validate identifier type
    if identifier_type not in SourceIdentifiers.VALID_TYPES:
        raise ValueError(f"Invalid identifier type. Must be one of: {SourceIdentifiers.VALID_TYPES}")
        
    # Search for existing source
    uuid_str, potential_matches = search_source(title, type, identifier_type, identifier_value, DB_PATH)
    if uuid_str:
        return {
            "status": "error",
            "message": "Source already exists",
            "existing_source": get_source_details(uuid_str, DB_PATH)
        }
    
    if potential_matches:
        return {
            "status": "error",
            "message": "Potential duplicates found. Please verify or use add_identifier if these are the same source.",
            "matches": potential_matches
        }
    
    # Create new source
    new_id = str(uuid.uuid4())
    identifiers = {identifier_type: identifier_value}
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Add source
            cursor.execute("""
                INSERT INTO sources (id, title, type, identifiers)
                VALUES (?, ?, ?, ?)
            """, [
                new_id,
                title,
                type,
                json.dumps(identifiers)
            ])
            
            # Add initial note if provided
            if initial_note:
                if not all(k in initial_note for k in ('title', 'content')):
                    raise ValueError("Initial note must contain 'title' and 'content'")
                    
                cursor.execute("""
                    INSERT INTO source_notes (source_id, note_title, content)
                    VALUES (?, ?, ?)
                """, [
                    new_id,
                    initial_note['title'],
                    initial_note['content']
                ])
            
            conn.commit()
            return {
                "status": "success",
                "source": get_source_details(new_id, DB_PATH)
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"Database error: {str(e)}")

@mcp.tool()
def add_note(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str,
    note_title: str,
    note_content: str
) -> Dict[str, Any]:
    """Add a new note to an existing source.
    
    Args:
        title: Source title
        type: Source type
        identifier_type: Type of identifier
        identifier_value: Value of the identifier
        note_title: Title for the new note
        note_content: Content of the note
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    # Find source
    uuid, potential_matches = search_source(title, type, identifier_type, identifier_value, DB_PATH)
    if not uuid:
        if potential_matches:
            return {
                "status": "error",
                "message": "Multiple potential matches found. Please verify the source.",
                "matches": potential_matches
            }
        return {
            "status": "error",
            "message": "Source not found"
        }
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Check if note with same title exists
            cursor.execute("""
                SELECT 1 FROM source_notes
                WHERE source_id = ? AND note_title = ?
            """, [uuid, note_title])
            
            if cursor.fetchone():
                return {
                    "status": "error",
                    "message": "Note with this title already exists for this source"
                }
            
            # Add new note
            cursor.execute("""
                INSERT INTO source_notes (source_id, note_title, content)
                VALUES (?, ?, ?)
            """, [uuid, note_title, note_content])
            
            conn.commit()
            return {
                "status": "success",
                "source": get_source_details(uuid, DB_PATH)
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"Database error: {str(e)}")

@mcp.tool()
def update_status(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str,
    new_status: str
) -> Dict[str, Any]:
    """Update source reading status.
    
    Args:
        title: Source title
        type: Source type
        identifier_type: Type of identifier
        identifier_value: Value of the identifier
        new_status: New status ('unread', 'reading', 'completed', 'archived')
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    if new_status not in SourceStatus.VALID_STATUS:
        raise ValueError(f"Invalid status. Must be one of: {SourceStatus.VALID_STATUS}")
    
    # Find source
    uuid, potential_matches = search_source(title, type, identifier_type, identifier_value, DB_PATH)
    if not uuid:
        if potential_matches:
            return {
                "status": "error",
                "message": "Multiple potential matches found. Please verify the source.",
                "matches": potential_matches
            }
        return {
            "status": "error",
            "message": "Source not found"
        }
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE sources 
                SET status = ?
                WHERE id = ?
            """, [new_status, uuid])
            
            conn.commit()
            return {
                "status": "success",
                "source": get_source_details(uuid, DB_PATH)
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"Database error: {str(e)}")

@mcp.tool()
def add_identifier(
    title: str,
    type: str,
    current_identifier_type: str,
    current_identifier_value: str,
    new_identifier_type: str,
    new_identifier_value: str
) -> Dict[str, Any]:
    """Add a new identifier to an existing source.
    
    Args:
        title: Source title
        type: Source type
        current_identifier_type: Current identifier type
        current_identifier_value: Current identifier value
        new_identifier_type: New identifier type to add
        new_identifier_value: New identifier value to add
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    # Validate new identifier type
    if new_identifier_type not in SourceIdentifiers.VALID_TYPES:
        raise ValueError(f"Invalid new identifier type. Must be one of: {SourceIdentifiers.VALID_TYPES}")
    
    # Find source by current identifier
    uuid, _ = search_source(title, type, current_identifier_type, current_identifier_value, DB_PATH)
    if not uuid:
        return {
            "status": "error",
            "message": "Source not found with current identifier"
        }
    
    # Check if new identifier already exists on any source
    check_uuid, _ = search_source(title, type, new_identifier_type, new_identifier_value, DB_PATH)
    if check_uuid and check_uuid != uuid:
        return {
            "status": "error",
            "message": "New identifier already exists on a different source",
            "existing_source": get_source_details(check_uuid, DB_PATH)
        }
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get current identifiers
            cursor.execute("SELECT identifiers FROM sources WHERE id = ?", [uuid])
            current_identifiers = json.loads(cursor.fetchone()['identifiers'])
            
            # Add new identifier
            current_identifiers[new_identifier_type] = new_identifier_value
            
            # Update source
            cursor.execute("""
                UPDATE sources 
                SET identifiers = ?
                WHERE id = ?
            """, [json.dumps(current_identifiers), uuid])
            
            conn.commit()
            return {
                "status": "success",
                "source": get_source_details(uuid, DB_PATH)
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"Database error: {str(e)}")


# Entity management tools

@mcp.tool()
def link_to_entity(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str,
    entity_name: str,
    relation_type: str,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Link a source to an entity in the knowledge graph.
    
    Args:
        title: Source title
        type: Source type
        identifier_type: Type of identifier
        identifier_value: Value of the identifier
        entity_name: Name of the entity to link to
        relation_type: Type of relationship
        notes: Optional notes explaining the relationship
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    if relation_type not in EntityRelations.VALID_TYPES:
        raise ValueError(f"Invalid relation type. Must be one of: {EntityRelations.VALID_TYPES}")
    
    # Find source
    uuid, potential_matches = search_source(title, type, identifier_type, identifier_value, DB_PATH)
    if not uuid:
        if potential_matches:
            return {
                "status": "error",
                "message": "Multiple potential matches found. Please verify the source.",
                "matches": potential_matches
            }
        return {
            "status": "error",
            "message": "Source not found"
        }
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Check if link already exists
            cursor.execute("""
                SELECT 1 FROM source_entity_links
                WHERE source_id = ? AND entity_name = ?
            """, [uuid, entity_name])
            
            if cursor.fetchone():
                return {
                    "status": "error",
                    "message": "Link already exists between this source and entity"
                }
            
            # Create link
            cursor.execute("""
                INSERT INTO source_entity_links 
                (source_id, entity_name, relation_type, notes)
                VALUES (?, ?, ?, ?)
            """, [uuid, entity_name, relation_type, notes])
            
            conn.commit()
            return {
                "status": "success",
                "source": get_source_details(uuid, DB_PATH)
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"Database error: {str(e)}")

@mcp.tool()
def get_source_entities(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str
) -> Dict[str, Any]:
    """Get all entities linked to a source.
    
    Args:
        title: Source title
        type: Source type
        identifier_type: Type of identifier
        identifier_value: Value of the identifier
    
    Returns:
        Dictionary containing the source's linked entities and their relationships
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    # Find source
    uuid, potential_matches = search_source(title, type, identifier_type, identifier_value, DB_PATH)
    if not uuid:
        if potential_matches:
            return {
                "status": "error",
                "message": "Multiple potential matches found. Please verify the source.",
                "matches": potential_matches
            }
        return {
            "status": "error",
            "message": "Source not found"
        }
    
    # Return full source details which include entity links
    return {
        "status": "success",
        "source": get_source_details(uuid, DB_PATH)
    }

@mcp.tool()
def update_entity_link(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str,
    entity_name: str,
    relation_type: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Update an existing link between a source and an entity.
    
    Args:
        title: Source title
        type: Source type
        identifier_type: Type of identifier
        identifier_value: Value of the identifier
        entity_name: Name of the entity
        relation_type: Optional new relationship type
        notes: Optional new notes
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    if relation_type and relation_type not in EntityRelations.VALID_TYPES:
        raise ValueError(f"Invalid relation type. Must be one of: {EntityRelations.VALID_TYPES}")
        
    if not relation_type and notes is None:
        raise ValueError("At least one of relation_type or notes must be provided")
    
    # Find source
    uuid, potential_matches = search_source(title, type, identifier_type, identifier_value, DB_PATH)
    if not uuid:
        if potential_matches:
            return {
                "status": "error",
                "message": "Multiple potential matches found. Please verify the source.",
                "matches": potential_matches
            }
        return {
            "status": "error",
            "message": "Source not found"
        }
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            updates = []
            params = []
            
            if relation_type:
                updates.append("relation_type = ?")
                params.append(relation_type)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
                
            params.extend([uuid, entity_name])
            
            query = f"""
                UPDATE source_entity_links 
                SET {', '.join(updates)}
                WHERE source_id = ? AND entity_name = ?
            """
            
            cursor.execute(query, params)
            if cursor.rowcount == 0:
                return {
                    "status": "error",
                    "message": "No link found between this source and entity"
                }
            
            conn.commit()
            return {
                "status": "success",
                "source": get_source_details(uuid, DB_PATH)
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"Database error: {str(e)}")

@mcp.tool()
def remove_entity_link(
    title: str,
    type: str,
    identifier_type: str,
    identifier_value: str,
    entity_name: str
) -> Dict[str, Any]:
    """Remove a link between a source and an entity.
    
    Args:
        title: Source title
        type: Source type
        identifier_type: Type of identifier
        identifier_value: Value of the identifier
        entity_name: Name of the entity
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    # Find source
    uuid, potential_matches = search_source(title, type, identifier_type, identifier_value, DB_PATH)
    if not uuid:
        if potential_matches:
            return {
                "status": "error",
                "message": "Multiple potential matches found. Please verify the source.",
                "matches": potential_matches
            }
        return {
            "status": "error",
            "message": "Source not found"
        }
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                DELETE FROM source_entity_links
                WHERE source_id = ? AND entity_name = ?
            """, [uuid, entity_name])
            
            if cursor.rowcount == 0:
                return {
                    "status": "error",
                    "message": "No link found between this source and entity"
                }
            
            conn.commit()
            return {
                "status": "success",
                "source": get_source_details(uuid, DB_PATH)
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"Database error: {str(e)}")

@mcp.tool()
def get_entity_sources(
    entity_name: str,
    type_filter: Optional[str] = None,
    relation_filter: Optional[str] = None
) -> Dict[str, Any]:
    """Get all sources linked to a specific entity with optional filtering.
    
    Args:
        entity_name: Name of the entity
        type_filter: Optional filter by source type
        relation_filter: Optional filter by relation type
    
    Returns:
        Dictionary containing the entity's linked sources
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    if type_filter and type_filter not in SourceTypes.VALID_TYPES:
        raise ValueError(f"Invalid type filter. Must be one of: {SourceTypes.VALID_TYPES}")
        
    if relation_filter and relation_filter not in EntityRelations.VALID_TYPES:
        raise ValueError(f"Invalid relation filter. Must be one of: {EntityRelations.VALID_TYPES}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            query = """
                SELECT s.*, l.relation_type, l.notes as relation_notes
                FROM sources s
                JOIN source_entity_links l ON s.id = l.source_id
                WHERE l.entity_name = ?
            """
            params = [entity_name]
            
            if type_filter:
                query += " AND s.type = ?"
                params.append(type_filter)
                
            if relation_filter:
                query += " AND l.relation_type = ?"
                params.append(relation_filter)
            
            cursor.execute(query, params)
            sources = []
            for row in cursor.fetchall():
                source_id = row['id']
                source_data = get_source_details(source_id, DB_PATH)
                sources.append(source_data)
            
            return {
                "status": "success",
                "entity": entity_name,
                "filters_applied": {
                    "type": type_filter,
                    "relation": relation_filter
                },
                "sources": sources
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"Database error: {str(e)}")






if __name__ == "__main__":
    # Start the FastMCP server
    mcp.run()