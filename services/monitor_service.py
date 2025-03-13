class MonitorService:
    """
    Service for managing shared state across the application.
    This service provides centralized access to:
    - active_monitors: tracking active monitoring tasks
    - user_queries: storing temporary user queries
    - user_filter_preferences: storing user filter preferences
    """
    
    def __init__(self):
        # Format: {chat_id: {query_id: task}}
        self.active_monitors = {}
        
        # Format: {chat_id: {query_id: {query: str, min_percentage: float, filter_mode: str}}}
        self.user_queries = {}
        
        # Format: {chat_id: "cex_only" or "all"}
        self.user_filter_preferences = {}
        
    def parse_filter_mode(self, callback_data: str) -> str:
        """
        Parse filter mode from callback data
        
        Args:
            callback_data: Callback data from the keyboard button (e.g., filter_cex, filter_all)
            
        Returns:
            filter_mode: Mode used in the application ("cex_only", "cex_dex_only", "future", "all")
        """
        # Strip "filter_" prefix from callback data
        mode = callback_data.replace("filter_", "")
        
        # Map callback mode to application mode
        if mode == "cex":
            return "cex_only"
        elif mode == "cex_dex_only":
            return "cex_dex_only"
        elif mode == "future":
            return "future"
        else:
            return "all"
            
    async def start_monitoring(self, user_id, query, bot, min_percentage, filter_mode, network=None, pool_address=None, query_id=None, enforce_deposit_withdrawal_checks=False):
        """
        Start monitoring a crypto asset for arbitrage opportunities
        
        Args:
            user_id: User or chat ID
            query: Coin/token symbol to monitor
            bot: The bot instance to use for sending messages
            min_percentage: Minimum arbitrage percentage to report
            filter_mode: Filtering mode (cex_only, cex_dex_only, future, all)
            network: Optional network for DEX operations
            pool_address: Optional pool address for DEX operations
            query_id: Optional query ID (generated if not provided)
            enforce_deposit_withdrawal_checks: Whether to enforce deposit/withdrawal checks
            
        Returns:
            dict: Result with success status and monitoring details
        """
        import asyncio
        import uuid
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            # Generate query ID if not provided
            if not query_id:
                query_id = str(uuid.uuid4())
                
            # Store query information
            if user_id not in self.user_queries:
                self.user_queries[user_id] = {}
                
            self.user_queries[user_id][query_id] = {
                'query': query,
                'min_percentage': min_percentage,
                'filter_mode': filter_mode,
                'network': network,
                'pool_address': pool_address,
                'enforce_deposit_withdrawal_checks': enforce_deposit_withdrawal_checks
            }
            
            # Store filter preference for this user
            self.user_filter_preferences[user_id] = filter_mode
            
            # Initialize active_monitors for this user if not exists
            if user_id not in self.active_monitors:
                self.active_monitors[user_id] = {}
                
            # Cancel existing task with the same ID if exists
            if query_id in self.active_monitors[user_id]:
                self.active_monitors[user_id][query_id].cancel()
                
            # Import the monitor function dynamically to avoid circular imports
            from handlers.exchange_handlers import monitor_prices
            
            # Check if we have a valid bot instance
            if not bot:
                raise ValueError("No bot instance provided. A valid bot instance is required.")
            
            # Start the monitoring task
            task = asyncio.create_task(
                monitor_prices(
                    user_id, 
                    query, 
                    bot, 
                    min_percentage, 
                    network, 
                    pool_address, 
                    query_id,
                    filter_mode,  # Explicitly pass the filter_mode
                    enforce_deposit_withdrawal_checks  # Pass the deposit/withdrawal check parameter
                )
            )
            
            # Store the task
            self.active_monitors[user_id][query_id] = task
            
            return {
                "success": True,
                "message": f"Monitoring started for {query}",
                "query_id": query_id,
                "filter_mode": filter_mode
            }
            
        except Exception as e:
            logger.error(f"Error starting monitoring: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error starting monitoring: {str(e)}",
                "error": str(e),
                "query_id": query_id if 'query_id' in locals() else None
            }

    async def stop_all_monitoring(self):
        """Stop all active monitoring tasks"""
        import logging
        
        logger = logging.getLogger(__name__)
        stopped_count = 0
        details = []
        
        try:
            # Iterate through all active monitors and cancel them
            for chat_id, monitors in list(self.active_monitors.items()):
                for query_id, task in list(monitors.items()):
                    if not task.done():
                        task.cancel()
                        stopped_count += 1
                        
                        # Find the associated query information if available
                        coin_name = "Unknown"
                        
                        # Look through all chat_ids in user_queries to find this query_id
                        for chat_id_inner, chat_data in self.user_queries.items():
                            if query_id in chat_data:
                                coin_name = chat_data[query_id].get('query', 'Unknown')
                                # Clean up from user_queries as well
                                del chat_data[query_id]
                                break
                                
                        details.append(f"{coin_name} (ID: {query_id[:8]})")
                
                # Clear monitors for this chat_id
                self.active_monitors[chat_id].clear()
            
            # Clear our tracking completely
            self.active_monitors.clear()
            
            return {"count": stopped_count, "details": ", ".join(details) if details else "No details available"}
            
        except Exception as e:
            logger.error(f"Error stopping monitoring tasks: {str(e)}", exc_info=True)
            return {"count": stopped_count, "details": f"Error: {str(e)}"}
            
    async def stop_monitoring(self, monitor_id_prefix):
        """
        Stop a specific monitoring task by ID prefix
        
        Args:
            monitor_id_prefix: The beginning part of a UUID to identify which monitor to stop
            
        Returns:
            dict: Result with success status and details
        """
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            # Find the monitor in all chat_ids
            for chat_id, monitors in list(self.active_monitors.items()):
                for query_id, task in list(monitors.items()):
                    # Check if this query_id starts with the provided prefix
                    if query_id.startswith(monitor_id_prefix):
                        # Cancel the task if it's not done
                        if not task.done():
                            task.cancel()
                        
                        # Remove the task from active_monitors
                        del self.active_monitors[chat_id][query_id]
                        
                        # Get the coin name if available
                        coin_name = "Unknown"
                        for chat_id_inner, chat_data in self.user_queries.items():
                            if query_id in chat_data:
                                coin_name = chat_data[query_id].get('query', 'Unknown')
                                # Clean up from user_queries as well
                                del chat_data[query_id]
                                break
                        
                        # Clean up empty dictionaries
                        if not self.active_monitors[chat_id]:
                            del self.active_monitors[chat_id]
                            
                        return {
                            "success": True, 
                            "message": f"Monitoring stopped for {coin_name}",
                            "query_id": query_id,
                            "coin": coin_name
                        }
            
            # If we get here, the monitor wasn't found
            return {
                "success": False,
                "error": f"No monitor found with ID: {monitor_id_prefix}"
            }
            
        except Exception as e:
            logger.error(f"Error stopping monitor {monitor_id_prefix}: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"Error stopping monitor: {str(e)}"
            }

    async def list_all_monitors(self):
        """List all active monitors"""
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            # Prepare list of monitor information
            monitors_info = []
            
            # Use our internal active_monitors
            # Iterate through all active monitors
            for chat_id, monitors in self.active_monitors.items():
                for query_id, task in monitors.items():
                    # Skip cancelled or done tasks
                    if task.done():
                        continue
                        
                    # Find the associated query information
                    query_info = "Unknown"
                    filter_mode = "all"
                    min_percentage = 0.1  # Default MIN_ARBITRAGE_PERCENTAGE
                    
                    # Look through all chat_ids in user_queries to find this query_id
                    for chat_id_inner, chat_data in self.user_queries.items():
                        if query_id in chat_data:
                            query_info = chat_data[query_id].get('query', 'Unknown')
                            filter_mode = chat_data[query_id].get('filter_mode', 'all')
                            min_percentage = chat_data[query_id].get('min_percentage', 0.1)
                            break
                    
                    # Format the filter mode for display
                    if filter_mode == "dex_only":
                        mode_text = "DEX Only"
                    elif filter_mode == "cex_only":
                        mode_text = "CEX-CEX Only"
                    elif filter_mode == "cex_dex_only":
                        mode_text = "CEX-DEX Only"
                    elif filter_mode == "future":
                        mode_text = "Futures Only (DEX-CEX-F)"
                    else:
                        mode_text = "All Types"
                    
                    monitors_info.append(f"• {query_info} (ID: {query_id[:8]})\n  - {mode_text}\n  - Min: {min_percentage}%")
            
            return monitors_info
            
        except Exception as e:
            logger.error(f"Error listing monitors: {str(e)}", exc_info=True)
            return []